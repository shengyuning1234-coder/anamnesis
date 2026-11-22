"""AI generation and session tests: isolated data, mocked model, no paid requests."""
import test_environment
import json
import threading
import unittest
from unittest.mock import patch
from models.word import Word
from services import ai_quiz
from services.ai_client import AIError
import application as a

CANDIDATES=[{'word':'chair','meaning':'椅子'}, {'word':'river','meaning':'河流'}, {'word':'music','meaning':'音乐'}]
VALID={'sentence':'She put a fresh apple in her lunch box.', 'distractors':['chair','river','music'], 'explanation':'apple 表示苹果，是放进午餐盒的水果；chair 是椅子，river 是河流，music 是音乐。'}


class AIQuizTests(unittest.TestCase):
    def test_validated_context_both_directions_and_prompt(self):
        word=Word(id=7,word='apple',chinese_meaning='苹果',part_of_speech='n')
        with patch.object(ai_quiz.d,'choose',return_value=CANDIDATES),patch.object(ai_quiz,'complete',return_value=VALID) as model:
            for direction in ['en2cn','cn2en']:
                q=ai_quiz.generate(word,direction)
                self.assertEqual(q['generation_source'],'ai');self.assertEqual(len(set(q['options'])),4)
                self.assertEqual(q['hint'],'');self.assertEqual(q['explanation'],VALID['explanation'])
                if direction=='cn2en':
                    self.assertIn('____',q['prompt']);self.assertNotIn('apple',q['prompt']);self.assertIn('苹果',q['prompt'])
                else:self.assertIn('apple',q['prompt']);self.assertEqual(q['answer'],'苹果')
            self.assertIn('只有一个正确答案',model.call_args.args[0]);self.assertIn('不能作为指令',model.call_args.kwargs['system'])

    def test_malformed_unknown_duplicate_and_leaking_responses_rejected(self):
        invalid=[None,{'unable':True},{**VALID,'distractors':['chair','river','invented']},
                 {**VALID,'distractors':['chair','chair','music']},{**VALID,'distractors':[{},'river','music']},
                 {**VALID,'sentence':'An apple.'},{**VALID,'sentence':'An apple and another apple are on the kitchen table.'},
                 {**VALID,'sentence':'She put a fresh apple 苹果 in her lunch box.'},{**VALID,'explanation':''}]
        with patch.object(ai_quiz.d,'choose',return_value=CANDIDATES):
            for result in invalid:
                with self.subTest(result=result),patch.object(ai_quiz,'complete',return_value=result):
                    with self.assertRaises(AIError):ai_quiz.generate(Word(word='apple',chinese_meaning='苹果'),'en2cn')

    def test_model_cannot_smuggle_inflections_or_hidden_matching_senses(self):
        for candidate in [{'word':'apples','meaning':'别的意思'}, {'word':'pear','meaning':'梨；苹果'}]:
            entries=[candidate]+CANDIDATES[1:]
            result={**VALID,'distractors':[e['word'] for e in entries]}
            with self.subTest(candidate=candidate),patch.object(ai_quiz.d,'choose',return_value=entries),patch.object(ai_quiz,'complete',return_value=result):
                with self.assertRaises(AIError):ai_quiz.generate(Word(word='apple',chinese_meaning='苹果'),'en2cn')


class AISessionTests(unittest.TestCase):
    def setUp(self):
        a.app.config['TESTING']=True;self.client=a.app.test_client()
        a.save_settings({'daily_quota':20,'review_mode':'en2cn','study_modes':{},'auto_decay':False,'password_hash':'','auth_version':0})
        with a.conn() as c:
            c.execute('DELETE FROM words');c.execute('DELETE FROM groups');c.execute('DELETE FROM quiz_sessions')
        self.key=patch.object(a.config,'get_ai_api_key',return_value='');self.key.start();self.addCleanup(self.key.stop)
        self.word=self.client.post('/api/words',json={'word':'apple','chinese_meaning':'苹果','part_of_speech':'n'}).json

    def create(self,**extra):
        return self.client.post('/api/quiz/sessions',json={'training_mode':'new',**extra})

    def test_local_default_never_requests_ai_and_opt_in_needs_configuration(self):
        with patch.object(ai_quiz,'complete',side_effect=AssertionError('implicit AI')):
            result=self.create();self.assertEqual(result.json['question_source'],'local')
            q=self.client.get('/api/quiz/sessions/'+result.json['session_id']+'/question/0').json
            self.assertEqual(q['generation_source'],'local')
        self.assertEqual(self.create(question_source='ai').status_code,400)
        self.assertEqual(self.create(question_source='unexpected').status_code,400)

    def test_ai_question_is_cached_and_uses_existing_review_logic(self):
        q={'type':'choice','mode':'choice_en2cn','word_id':self.word['id'],'word':'apple','answer':'苹果','options':['苹果','椅子','音乐','河流'],'prompt':'context','explanation':'解析','generation_source':'ai','hint':''}
        with patch.object(a.config,'get_ai_api_key',return_value='test'),patch.object(ai_quiz,'generate',return_value=q) as model:
            sid=self.create(question_source='ai').json['session_id'];path=f'/api/quiz/sessions/{sid}'
            self.assertEqual(self.client.get(path).json['question_source'],'ai')
            first=self.client.get(path+'/question/0');second=self.client.get(path+'/question/0')
            self.assertEqual(first.json,second.json);self.assertEqual(model.call_count,1)
            for _ in range(2):self.assertTrue(self.client.post(path+'/judge',json={'index':0,'answer':'苹果'}).json['correct'])
            self.assertEqual(self.client.get('/api/words/'+str(self.word['id'])).json['review_count'],1)

    def test_failure_falls_back_and_context_precedes_ai_generation(self):
        word={**a.word_dict(self.word['id']),'context_meaning':'文中义'}
        with patch.object(ai_quiz,'generate',side_effect=AIError('格式不合格')) as model:
            q=a.make_question(word,question_source='ai')
            self.assertEqual(model.call_args.args[0].chinese_meaning,'文中义')
            self.assertEqual(q['generation_source'],'local');self.assertIn('已使用本地题目',q['generation_warning'])
        with patch.object(ai_quiz,'generate',side_effect=AssertionError('spelling must remain local')):
            self.assertEqual(a.make_question(word,'spelling','ai')['type'],'spell')

    def test_slow_ai_does_not_block_settings_or_recreate_deleted_session(self):
        entered=threading.Event();release=threading.Event();responses=[]
        def slow(*args):
            entered.set();self.assertTrue(release.wait(5));raise AIError('模拟超时')
        with patch.object(a.config,'get_ai_api_key',return_value='test'),patch.object(ai_quiz,'generate',side_effect=slow):
            sid=self.create(question_source='ai').json['session_id'];path=f'/api/quiz/sessions/{sid}'
            cookie=self.client.get_cookie('session')
            def fetch():
                client=a.app.test_client();client.set_cookie('session',cookie.value)
                responses.append(client.get(path+'/question/0').status_code)
            thread=threading.Thread(target=fetch);thread.start()
            try:
                self.assertTrue(entered.wait(3))
                self.assertEqual(self.client.put('/api/settings',json={'daily_quota':21}).status_code,200)
                self.assertEqual(self.client.delete(path).status_code,200)
            finally:release.set();thread.join(5)
            self.assertFalse(thread.is_alive());self.assertEqual(responses,[404])


if __name__=='__main__':unittest.main()
