"""Integration checks use a disposable database and never call a remote AI."""
import os, tempfile, unittest, json, io, time, threading
from unittest.mock import patch
import test_environment  # Enforce isolation even when another test imports config first.
import application as a
from services.ai_client import parse_json, AIError
from PIL import Image


class UpgradeTests(unittest.TestCase):
    def setUp(self):
        a.app.config['TESTING']=True; self.client=a.app.test_client()
        a.save_settings({'daily_quota':20,'password_hash':'','auth_version':0,'scheduling_mode':'ebbinghaus','auto_decay':False})
        with a.conn() as c:
            c.execute('DELETE FROM words'); c.execute('DELETE FROM groups'); c.execute('DELETE FROM jobs'); c.execute('DELETE FROM quiz_sessions'); c.execute('DELETE FROM review_operations')
        self.key=patch.object(a.config,'get_ai_api_key',return_value=''); self.key.start(); self.addCleanup(self.key.stop)

    def post(self,path,data): return self.client.post(path,json=data)
    def word(self,text='apple',**kwargs):
        r=self.post('/api/words',{'word':text,'chinese_meaning':'苹果\n苹果树','notes':'第一行\n第二行',**kwargs}); self.assertEqual(r.status_code,201,r.json); return r.json['id']
    def group(self,name='阅读'): return self.post('/api/groups',{'name':name,'tags':['课程']}).json['id']

    def test_public_lexicons_and_local_classification(self):
        self.assertGreater(a.lexicon.status()['counts']['entries'],700000)
        local=a.lexicon.build_record('apple',None)
        self.assertTrue(local['chinese_meaning']);self.assertTrue(local['english_meaning'])
        self.assertIn('ECDICT',local['dictionary_sources'])
        self.assertIn('小学',a.lexicon.local_tags('apple'))
        with patch.object(a,'complete',side_effect=AssertionError('local match must not call AI')):
            wid=self.word(tags=['自定义'])
            classified=a.classify_word(wid)
            self.assertEqual(classified['source'],'local')
            self.assertIsNone(classified['categories']['商务'])
            self.assertIn('自定义',classified['tags']);self.assertIn('小学',classified['tags'])
            self.assertEqual(a.word_dict(wid)['classification_status'],'local')
        with patch.object(a.lexicon,'local_tags',return_value=[]),patch.object(a.config,'get_ai_api_key',return_value='test-key'):
            unknown=self.word('zzznolocalclassificationzzz')
            self.assertEqual(a.word_dict(unknown)['classification_status'],'pending')
            self.assertTrue(any(j['kind']=='classify' for j in self.client.get('/api/jobs').json))

    def test_bilingual_originals_survive_ai_enhancement(self):
        primary={'chinese_meaning':'原始中文义项','english_meaning':'original English sense','senses':[{'chinese':'原始中文义项','english':'original English sense'}],'examples':[('Original example.','原始例句。')]}
        with patch.object(a.local_dict,'query',return_value=primary),patch.object(a.config,'get_ai_api_key',return_value='test-key'):
            with patch.object(a,'complete',side_effect=AssertionError('local mode must not call AI')):
                base=a.lookup_data('apple',False)['data']
            with patch.object(a,'complete',return_value={'chinese_meaning':'错误改写','english_meaning':'rewritten','example_sentence':'rewritten','supplemental_notes':'补充搭配，供核对'}):
                enhanced=a.lookup_data('apple',True)['data']
            for field in ['chinese_meaning','english_meaning','example_sentence','example_translation','dictionary_references']:
                self.assertEqual(enhanced[field],base[field])
            self.assertTrue(enhanced['notes'].startswith(base['notes']))
            self.assertIn('AI 补充',enhanced['notes'])
            with patch.object(a,'complete',side_effect=AIError('offline')):
                fallback=a.lookup_data('apple',True)
                self.assertEqual(fallback['data'],base);self.assertEqual(fallback['source'],'local')
        with patch.object(a.local_dict,'query',return_value=None),patch.object(a.config,'get_ai_api_key',return_value='test-key'),patch.object(a,'complete',side_effect=AssertionError('no implicit AI')):
            self.assertFalse(a.lookup_data('zzznolocaldictionaryzzz',False)['found'])

    def test_ai_lookup_requires_explicit_boolean_and_configuration(self):
        record={'word':'test','chinese_meaning':'测试','notes':'词典原文','source':'local'}
        with patch.object(a.lexicon,'build_record',return_value=record.copy()),patch.object(a.local_dict,'query',return_value=None),patch.object(a,'complete') as ai:
            result=self.post('/api/words/lookup',{'word':'test','enhance':True}).json
            self.assertEqual(result['source'],'local');self.assertIn('尚未配置',result['warning']);ai.assert_not_called()
            with patch.object(a.config,'get_ai_api_key',return_value='test-key'):
                for opt in [None,False,'true','false',1]:
                    self.assertEqual(self.post('/api/words/lookup',{'word':'test','enhance':opt}).json['source'],'local')
                ai.assert_not_called()

    def test_ai_prompt_fills_only_missing_fields(self):
        record={'word':'apple','phonetic':'original IPA','part_of_speech':'noun','chinese_meaning':'原释义','english_meaning':'original definition','example_sentence':'','example_translation':'','notes':'原笔记','source':'local','dictionary_references':[]}
        generated={'phonetic':'rewritten IPA','part_of_speech':'verb','example_sentence':'An apple a day.','example_translation':'一天一个苹果。','supplemental_notes':'AI 补充：apple pie 苹果派'}
        with patch.object(a.lexicon,'build_record',side_effect=lambda *args: record.copy()),patch.object(a.local_dict,'query',return_value=None),patch.object(a.config,'get_ai_api_key',return_value='test-key'),patch.object(a,'complete',return_value=generated) as ai:
            result=self.post('/api/words/lookup',{'word':'apple','enhance':True}).json
            self.assertEqual(result['source'],'local+ai');self.assertEqual(result['data']['phonetic'],'original IPA')
            self.assertEqual(result['data']['chinese_meaning'],'原释义');self.assertEqual(result['data']['example_sentence'],generated['example_sentence'])
            self.assertTrue(result['data']['notes'].startswith('原笔记'));self.assertIn('apple pie',result['data']['notes'])
            prompt=ai.call_args.args[0];self.assertIn('至少两个',prompt);self.assertIn('原释义',prompt);self.assertIn('example_translation',prompt)

    def test_parser_keeps_idioms_separate(self):
        html='<li class="sense"><span class="def">a fruit</span><deft><chn class="simple">苹果</chn></deft></li><span class="idm-g"><span class="idm">the apple of your eye</span><li class="sense"><span class="def">someone loved</span><deft><chn class="simple">掌上明珠</chn></deft></li></span>'
        result=a.local_dict._parse_entry(html)
        self.assertEqual(result['chinese_meaning'],'苹果');self.assertEqual(result['english_meaning'],'a fruit')
        self.assertEqual(result['related_senses'][0]['phrase'],'the apple of your eye')
        record=a.lexicon.build_record('apple',result)
        self.assertIn('the apple of your eye',record['notes']);self.assertNotIn('掌上明珠',record['chinese_meaning'])

    def test_duplicate_preserves_progress(self):
        wid=self.word(); self.post('/api/review/'+str(wid),{'rating':5})
        r=self.post('/api/words',{'word':' APPLE ','chinese_meaning':'更新'}); self.assertEqual(r.status_code,409)
        r=self.post('/api/words',{'word':'APPLE','chinese_meaning':'更新','update_existing':True}); self.assertEqual(r.json['id'],wid); self.assertEqual(r.json['review_count'],1)
        self.assertEqual(r.json['notes'],'第一行\n第二行'); self.assertEqual(len(self.client.get('/api/words').json),1)

    def test_material_intake_local_first_and_atomic_save(self):
        wid=self.word(); gid=self.group()
        r=self.post('/api/intake/analyze',{'text':'Apple apple pear unknownword'}).json
        self.assertEqual(r['tokens'],4); self.assertEqual(len(r['words']),3)
        self.assertEqual(r['words'][0]['existing_id'],wid)
        with patch.object(a.local_dict,'query',return_value=None),patch.object(a,'complete',side_effect=AssertionError('implicit AI')):
            d=self.post('/api/intake/definitions',{'words':['unknownword']})
            self.assertFalse(d.json['words'][0]['found'])
        entries=[{'word':'pear','chinese_meaning':'梨','source':'local'},{'word':'unknownword'}]
        self.assertEqual(self.post('/api/intake/save',{'group_id':gid,'entries':entries}).status_code,400)
        self.assertEqual(len(self.client.get('/api/words').json),1)
        result=self.post('/api/intake/save',{'group_id':gid,'entries':[entries[0],{'word':'apple','chinese_meaning':'不应覆盖'}]})
        self.assertEqual(result.status_code,200,result.json); self.assertEqual(result.json['added'],1)
        self.assertEqual(a.word_dict(wid)['chinese_meaning'],'苹果\n苹果树')
        self.assertEqual(len(self.client.get(f'/api/words?group_id={gid}').json),2)

    def test_material_image_vision(self):
        content=io.BytesIO(); Image.new('RGB',(20,20),'white').save(content,'PNG');content.seek(0)
        with patch.object(a,'complete',return_value={'text':'apple pear'}) as vision:
            r=self.client.post('/api/intake/image',data={'image':(content,'page.png')},content_type='multipart/form-data')
            self.assertEqual(r.status_code,200,r.json); self.assertEqual(r.json['text'],'apple pear')
            self.assertEqual(vision.call_args.args[0][1]['type'],'image_url')
        r=self.client.post('/api/intake/image',data={'image':(io.BytesIO(b'bad'),'bad.png')},content_type='multipart/form-data')
        self.assertEqual(r.status_code,400)

    def test_context_meaning_is_filtered_before_answer_shuffle(self):
        from services.local_dict import local_dict
        wid=self.word(context_meaning='')
        source=a.word_dict(wid);source['context_meaning']='决定'
        candidates=[{'word':'determine','meaning':'确定；决定'},
                    {'word':'receive','meaning':'接收'},
                    {'word':'reduce','meaning':'减少'},
                    {'word':'remember','meaning':'记住'}]
        with patch.object(a,'settings',return_value={'study_modes':{},'review_mode':'en2cn'}), \
             patch.object(local_dict,'distractors',return_value=candidates) as lookup, \
             patch('services.quiz_service.random.shuffle',side_effect=lambda xs: xs.reverse()):
            q=a.make_question(source)
        self.assertEqual(q['type'],'choice')
        self.assertEqual(q['answer'],'决定')
        self.assertEqual(q['options'][0],'决定')
        self.assertEqual(set(q['options']),{'决定','接收','减少','记住'})
        self.assertEqual(lookup.call_args.args[2],'决定')
        self.assertEqual(source['chinese_meaning'],'苹果\n苹果树')

    def test_group_context_and_cascades(self):
        g1,g2=self.group(),self.group('其他'); wid=self.word(group_id=g1,context_meaning='文中义一')
        self.client.put(f'/api/groups/{g2}/words/{wid}',json={'context_meaning':'文中义二'})
        self.assertNotIn('context_meaning',self.client.get(f'/api/words/{wid}').json)
        self.assertEqual(self.client.get(f'/api/words/{wid}?group_id={g2}').json['context_meaning'],'文中义二')
        self.client.delete(f'/api/groups/{g1}'); self.assertEqual(self.client.get(f'/api/words/{wid}').status_code,200)
        self.client.delete(f'/api/words/{wid}')
        with a.conn() as c: self.assertEqual(c.execute('SELECT COUNT(*) FROM group_words').fetchone()[0],0)

    def test_quota_and_quiz_idempotency(self):
        ids=[self.word(w) for w in ['apple','pear','cat']]
        self.assertEqual(self.client.get('/api/stats/today').json['today']['new_words_learned'],0)
        self.client.put('/api/settings',json={'daily_quota':1,'study_modes':{'test':'meaning_only'}})
        s=self.post('/api/quiz/sessions',{'training_mode':'new'}).json; self.assertEqual(s['total'],1)
        sid=s['session_id']; self.client.get(f'/api/quiz/sessions/{sid}/question/0')
        x=self.post(f'/api/quiz/sessions/{sid}/judge',{'index':0,'answer':'remember'}); self.assertEqual(x.status_code,200,x.json)
        x=self.post(f'/api/quiz/sessions/{sid}/judge',{'index':0,'answer':'remember'}); self.assertEqual(x.status_code,200)
        self.assertEqual(a.word_dict(s['words'][0]['id'])['review_count'],1)
        self.assertEqual(self.post('/api/quiz/sessions',{'training_mode':'new'}).json['total'],0)
        self.assertEqual(self.post('/api/review/'+str(ids[1]),{'rating':5}).status_code,409)
        self.assertEqual(self.client.get('/api/stats/today').json['daily_quota'],1)
        self.assertEqual(self.post('/api/session/end',{}).json['new_words_learned'],1)

    def test_fsrs_and_offline_dedup(self):
        wid=self.word(); self.client.put('/api/settings',json={'scheduling_mode':'fsrs'})
        op={'operation_id':'unique-offline-op','word_id':wid,'rating':4,'mode':'spell_en','reviewed_at':a.now()}
        r=self.post('/api/review/sync',{'operations':[op,op]}); self.assertEqual([x['status'] for x in r.json['results']],['applied','duplicate'],r.json)
        self.assertEqual(a.word_dict(wid)['review_count'],1)
        with a.conn() as c: self.assertIsNotNone(c.execute('SELECT card FROM fsrs_cards').fetchone())

    def test_backup_roundtrip_and_rollback(self):
        gid=self.group(); wid=self.word(group_id=gid,context_meaning='文中义'); self.post('/api/review/'+str(wid),{'rating':5})
        export=self.client.get('/api/words/export').json
        with a.conn() as c: c.execute('DELETE FROM words'); c.execute('DELETE FROM groups')
        def restore(d): return self.client.post('/api/words/import',data={'file':(io.BytesIO(json.dumps(d).encode()),'backup.json'),'overwrite':'true'},content_type='multipart/form-data')
        r=restore(export); self.assertEqual(r.status_code,200,r.json); words=self.client.get('/api/words').json; self.assertEqual(words[0]['review_count'],1)
        group=self.client.get('/api/groups').json[0]; self.assertEqual(self.client.get(f"/api/words?group_id={group['id']}").json[0]['context_meaning'],'文中义')
        export['words'].append({'id':100,'word':'bad','proficiency':'INVALID'})
        r=restore(export); self.assertEqual(r.status_code,400)
        self.assertEqual(len(self.client.get('/api/words').json),1)
        self.assertTrue(self.client.get('/api/backup/database').data.startswith(b'SQLite format 3'))

    def test_mcp_auth_and_tools(self):
        self.assertEqual(self.post('/mcp',{}).status_code,401)
        self.assertEqual(self.client.get('/api/settings',headers={'Authorization':'Bearer '+a.MCP_TOKEN}).status_code,403)
        def rpc(method,params={}): return self.client.post('/mcp',json={'jsonrpc':'2.0','id':1,'method':method,'params':params},headers={'Authorization':'Bearer '+a.MCP_TOKEN}).json['result']
        self.assertEqual(rpc('initialize',{'protocolVersion':'2025-06-18'})['protocolVersion'],'2025-06-18')
        self.assertGreater(len(rpc('tools/list')['tools']),8)
        result=rpc('tools/call',{'name':'create_group','arguments':{'name':'MCP 测试'}}); gid=json.loads(result['content'][0]['text'])['id']
        result=rpc('tools/call',{'name':'save_full_definition','arguments':{'definition':{'word':'test','chinese_meaning':'测试'},'groups':[{'group_id':gid,'context_meaning':'测验'}]}}); self.assertFalse(result['isError'])
        result=rpc('tools/call',{'name':'query_words','arguments':{'group_id':gid}}); self.assertEqual(json.loads(result['content'][0]['text'])[0]['context_meaning'],'测验')
        result=rpc('tools/call',{'name':'save_word','arguments':{'word':'oops','password_hash':'bad'}}); self.assertTrue(result['isError'])

    def test_settings_zero_background_and_auth(self):
        r=self.client.put('/api/settings',json={'appearance':{'background_blur':0,'card_opacity':40},'daily_quota':11}); self.assertEqual(r.status_code,200)
        self.assertEqual(self.client.get('/api/settings').json['appearance']['background_blur'],0)
        pic=io.BytesIO(); Image.new('RGB',(20,20),'#456789').save(pic,format='PNG'); pic.seek(0)
        r=self.client.post('/api/settings/background/upload',data={'file':(pic,'x.png')}); self.assertEqual(r.status_code,200,r.json); response=self.client.get(r.json['path']); self.assertEqual(response.status_code,200); response.close()
        self.assertEqual(self.post('/api/auth/setup',{'password':'secret123'}).status_code,200)
        other=a.app.test_client(); self.assertEqual(other.get('/api/words').status_code,401)
        self.assertEqual(other.post('/api/auth/login',json={'password':'secret123','remember':True}).status_code,200)
        with other.session_transaction() as session: self.assertGreater(session['expires_at']-time.time(),179*86400)
        self.post('/api/auth/change-password',{'old_password':'secret123','new_password':'newpass123'})
        self.assertEqual(other.get('/api/words').status_code,401)
        self.assertEqual(self.client.get('/login').status_code,200)

    def test_ai_json_and_retry(self):
        self.assertEqual(parse_json('<think>no</think>说明```json\n{"ok":true}\n```'),{'ok':True})
        from services import ai_client
        with patch.object(ai_client,'get_ai_api_key',return_value='test'), patch.object(ai_client.urllib.request,'build_opener') as opener, patch.object(ai_client.time,'sleep'):
            opener.return_value.open.side_effect=[OSError(),OSError(),OSError()]
            with self.assertRaises(AIError): ai_client.complete('test')
            self.assertEqual(opener.return_value.open.call_count,3)

    def test_durable_queue_and_classification(self):
        with patch.object(a.local_dict,'query',return_value={'chinese_meaning':'本地释义','examples':[]}):
            self.assertTrue(a.lookup_data('test',True)['found'])
        gid=self.group(); r=self.post('/api/quick-entry',{'group_id':gid,'entries':[{'word':'queueword','context_meaning':'文中意思'}]}); self.assertEqual(r.status_code,202)
        stop=threading.Event()
        with patch.object(a,'lookup_data',return_value={'found':True,'data':{'word':'queueword','chinese_meaning':'词典完整释义'}}):
            thread=threading.Thread(target=a.worker,args=(stop,),daemon=True); thread.start()
            try:
                for _ in range(50):
                    job=self.client.get('/api/jobs').json[0]
                    if job['status'] in ('done','failed'): break
                    time.sleep(.05)
                self.assertEqual(job['status'],'done',job)
            finally: stop.set(); thread.join(2)
        word=self.client.get(f'/api/words?group_id={gid}').json[0]; self.assertEqual(word['context_meaning'],'文中意思')
        flags={k:k in ('小学','日常') for k in a.CATEGORIES}
        with patch.object(a,'complete',return_value={'categories':flags}):
            r=self.post('/api/words/classify',{'word_id':word['id']}); self.assertEqual(r.json['tags'],['小学','日常'])
        with patch.object(a,'complete',return_value={'categories':{'小学':'true'}}):
            self.assertEqual(self.post('/api/words/classify',{'word_id':word['id']}).status_code,502)

    def test_wordbook_feeds_new_learning(self):
        csv='word,chinese_meaning\nbookapple,苹果\nbookpear,梨\n'
        r=self.client.post('/api/wordbooks/import',data={'file':(io.BytesIO(csv.encode()),'lesson.csv')}); self.assertEqual(r.status_code,200,r.json)
        self.client.put('/api/settings',json={'daily_quota':2})
        r=self.post('/api/quiz/sessions',{'training_mode':'new'}); self.assertEqual(r.status_code,200,r.json); self.assertEqual(r.json['total'],2)
        self.assertEqual(self.client.get('/api/wordbooks').json[0]['imported_count'],2)

    def test_legacy_background_does_not_block_ai_settings(self):
        legacy='/static/uploads/background/settings-fixture.png'
        a.save_settings({'appearance':{'background_type':'custom','background_image_path':legacy}})
        directory=a.DATA/'uploads/background';directory.mkdir(parents=True,exist_ok=True)
        Image.new('RGB',(32,24),'blue').save(directory/'settings-fixture.png')
        with patch.dict(os.environ,{'BUNDLED_WEBUI':'1'}), patch.object(a.config,'save_apikey',return_value=True) as save:
            current=self.client.get('/api/settings').json
            self.assertEqual(current['appearance']['background_image_path'],'/api/background/legacy/settings-fixture.png')
            current.update(api_key='test-placeholder-key',openwebui_url='/')
            response=self.client.put('/api/settings',json=current)
            self.assertEqual(response.status_code,200,response.json)
            save.assert_called_once_with('test-placeholder-key')
        response=self.client.get('/api/background/legacy/settings-fixture.png')
        self.assertEqual(response.status_code,200);response.close()
        a.save_settings({'appearance':{'background_type':'default','background_image_path':''}})

    def test_api_key_save_failure_is_reported(self):
        with patch.object(a.config,'save_apikey',return_value=False):
            response=self.client.put('/api/settings',json={'api_key':'test-placeholder-key'})
        self.assertEqual(response.status_code,500)
        self.assertIn('/data/words',response.json['error'])
        self.assertNotIn('saved',response.json)

    def test_api_key_atomic_persistence_and_blank_preserves(self):
        self.key.stop()
        with tempfile.TemporaryDirectory() as directory, patch.object(a.config,'_DATA_DIR',directory), patch.object(a.config,'_APIKEY_FILE',os.path.join(directory,'.apikey')), patch.object(a.config,'_cached_apikey',None):
            response=self.client.put('/api/settings',json={'api_key':'  test-placeholder-key  '})
            self.assertEqual(response.status_code,200,response.json)
            self.assertTrue(response.json['has_key'])
            a.config._cached_apikey=None
            self.assertEqual(a.config.get_ai_api_key(),'test-placeholder-key')
            response=self.client.put('/api/settings',json={'api_key':''})
            self.assertEqual(response.status_code,200)
            self.assertEqual(a.config.get_ai_api_key(),'test-placeholder-key')
            self.assertEqual(os.stat(os.path.join(directory,'.apikey')).st_mode & 0o777,0o600)
            self.assertEqual(self.client.put('/api/settings',json={'clear_api_key':True}).status_code,200)
            self.assertFalse(a.config.get_ai_api_key())


if __name__=='__main__': unittest.main(verbosity=2)
