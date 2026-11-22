"""Regression fixtures for ambiguous vocabulary choices; no network/AI or user data."""
import test_environment  # Must precede imports that load config.
import random
import unittest
from unittest.mock import patch
from concurrent.futures import ThreadPoolExecutor
from models.word import Word
from services import distractors as d
from services.quiz_service import QuizService
from services.local_dict import local_dict


class DistractorTests(unittest.TestCase):
    def test_inflections_irregulars_derivations_and_synonyms(self):
        for a,b in [('run','running'),('study','studies'),('walk','walked'),('go','went'),
                    ('take','taken'),('mouse','mice'),('good','better'),('decide','decision'),
                    ('happy','happiness'),('organise','organization'),('color','colour'),
                    ('buy','purchase'),('big','large'),('quick','fast'),('teacher','lecturer')]:
            with self.subTest(a=a,b=b):self.assertTrue(d.english_conflict(a,b))
        for a,b in [('apple','lemon'),('decide','receive'),('happy','legal')]:
            with self.subTest(a=a,b=b):self.assertFalse(d.english_conflict(a,b))

    def test_chinese_near_duplicates_and_hidden_senses(self):
        for a,b in [('① 快乐的','adj. 快乐'),('n. 决定；决心','v. 决定'),
                    ('获得；取得','得到；取得'),('有意义的','有意思的'),
                    ('苹果, 苹果树','n. 苹果树'),('有效的','无效的'),('进口','出口')]:
            with self.subTest(a=a,b=b):self.assertTrue(d.chinese_conflict(a,b))
        self.assertFalse(d.chinese_conflict('苹果','柠檬'))
        self.assertFalse(d.chinese_conflict('教师','律师'))
        self.assertEqual(d.first_meaning('①苹果\n②苹果树'),'苹果')

    def test_pos_is_not_an_indefinite_article_in_english_definition(self):
        self.assertEqual(d.parts_of_speech('','n. a fruit'),{'n'})
        self.assertEqual(d.parts_of_speech('','v. make a decision'),{'v'})
        self.assertEqual(d.parts_of_speech('','a. 快乐的'),{'a'})
        self.assertEqual(d.parts_of_speech('','an unknown thing'),set())

    def test_choice_glosses_strip_dictionary_pos_variants(self):
        quiz = QuizService(None)
        word = Word(id=7, word='blue', chinese_meaning='蓝色的')
        entries = [
            {'word': 'bright', 'meaning': '① a. & adv. 明亮的；明亮地'},
            {'word': 'chair', 'meaning': '［名词］椅子'},
            {'word': 'caution', 'meaning': '【n.】 小心，vt. 告诫'},
        ]
        with patch.object(local_dict, 'distractors', return_value=entries):
            result = quiz.generate_question(word, 'choice_en2cn')
        self.assertEqual(result['answer'], '蓝色的')
        self.assertEqual(set(result['options']), {'蓝色的', '明亮的', '椅子', '小心，告诫'})
        self.assertEqual(d.first_meaning('int. 嗯'), '嗯')
        self.assertEqual(d.first_meaning('（不及物）行走'), '（不及物）行走')
        self.assertEqual(d.first_meaning('名词短语'), '名词短语')

    def test_pairwise_filter_in_both_directions(self):
        target=Word(id=123,word='decide',chinese_meaning='决定；判决',part_of_speech='verb')
        entries=[{'word':'decision','meaning':'决定'},
                 {'word':'determine','meaning':'确定；决定'},
                 {'word':'receive','meaning':'接收'},
                 {'word':'receiving','meaning':'正在接收'},
                 {'word':'obtain','meaning':'获得；接收'},
                 {'word':'reduce','meaning':'减少'},
                 {'word':'remember','meaning':'记住'}]
        quiz=QuizService(None)
        with patch.object(local_dict,'distractors',return_value=entries):
            for mode in ['choice_en2cn','choice_cn2en']:
                question=quiz.generate_question(target,mode)
                self.assertEqual(question['type'],'choice');self.assertEqual(len(question['options']),4)
                expected={'决定','接收','减少','记住'} if mode=='choice_en2cn' else {'decide','receive','reduce','remember'}
                self.assertEqual(set(question['options']),expected)

    def test_insufficient_candidates_never_produces_a_weak_choice(self):
        quiz=QuizService(None);word=Word(id=9,word='apple',chinese_meaning='苹果')
        with patch.object(local_dict,'distractors',return_value=[{'word':'lemon','meaning':'柠檬'},{'word':'chair','meaning':'椅子'}]):
            for mode in ['choice_en2cn','choice_cn2en']:
                q=quiz.generate_question(word,mode)
                self.assertEqual(q['type'],'recall');self.assertNotIn('options',q)

    def test_dictionary_cold_start_and_parallel_requests(self):
        # MDX need not be indexed and the learner's word list need not supply peers.
        words=['apple','happy','decide','book','beautiful','run']
        def check(word):
            entry=d.reference(word);answers=d.choose(word,entry['translation'])
            self.assertEqual(len(answers),3)
            for i,a in enumerate(answers):
                self.assertFalse(d.english_conflict(word,a['word']))
                self.assertFalse(d.chinese_conflict(entry['translation'],a['meaning']))
                self.assertEqual(d.parts_of_speech('',entry['translation']),d.parts_of_speech('',a['meaning']))
                for b in answers[:i]:
                    self.assertFalse(d.english_conflict(a['word'],b['word']))
                    self.assertFalse(d.chinese_conflict(a['meaning'],b['meaning']))
            return answers
        with ThreadPoolExecutor(max_workers=4) as executor:list(executor.map(check,words))

    def test_topic_peers_do_not_use_obscure_alternate_senses(self):
        peers=d.sibling_words('apple')
        self.assertIn('grape',peers)
        self.assertNotIn('jack',peers)
        self.assertFalse(d.prominent_pos('natural','n'))
        self.assertTrue(d.prominent_pos('natural','a'))

    def test_absent_corpus_does_not_fall_back_to_unsafe_candidates(self):
        with patch.object(d,'wordnet',return_value=None):self.assertEqual(d.choose('apple','苹果'),[])


if __name__=='__main__':unittest.main()
