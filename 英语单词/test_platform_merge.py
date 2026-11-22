"""Merged platform checks: disposable data, no external AI requests."""
import json
import sqlite3
import unittest
from unittest.mock import patch

import test_environment
import application as a
import tenancy


class PlatformMergeTests(unittest.TestCase):
    def setUp(self):
        a.app.config['TESTING'] = True
        tenancy.profile.set('admin')
        with sqlite3.connect(tenancy.ROOT / 'accounts.db') as c:
            c.execute('DELETE FROM devices')
            c.execute("DELETE FROM users WHERE id!='admin'")
            c.execute("UPDATE users SET password='' WHERE id='admin'")
            c.execute('DELETE FROM preferences')
        with a.conn() as c:
            for table in ('words', 'groups', 'jobs', 'quiz_sessions', 'review_operations'):
                c.execute('DELETE FROM ' + table)
        a.save_settings({'password_hash': '', 'auto_decay': False, 'daily_quota': 20})
        self.client = a.app.test_client()
        self.assertEqual(self.client.post('/api/auth/setup', json={'password': 'merge-test-only'}).status_code, 200)
        self.ai = patch.object(a.config, 'resolve_ai', return_value={
            'key': '', 'base': 'https://example.invalid', 'model': 'test', 'own': False, 'proxy': ''})
        self.ai.start()
        self.addCleanup(self.ai.stop)

    def test_accounts_preserve_admin_and_isolate_words(self):
        self.assertEqual(self.client.post('/api/words', json={'word': 'apple', 'chinese_meaning': '苹果'}).status_code, 201)
        response = self.client.post('/api/admin/users', json={'username': 'tester', 'password': 'merge-test-only'})
        self.assertEqual(response.status_code, 201, response.json)
        other = a.app.test_client()
        self.assertEqual(other.post('/api/auth/login', json={'username': 'tester', 'password': 'merge-test-only'}).status_code, 200)
        self.assertEqual(other.get('/api/words').json, [])
        self.assertEqual(other.get('/api/admin/users').status_code, 403)
        self.assertEqual(len(self.client.get('/api/words').json), 1)
        self.assertEqual(other.post('/api/words', json={'word': 'pear', 'chinese_meaning': '梨'}, headers={'X-Account-ID': 'admin'}).status_code, 409)

    def test_session_survives_login_and_scores_once(self):
        word = self.client.post('/api/words', json={'word': 'apple', 'chinese_meaning': '苹果'}).json
        result = self.client.post('/api/quiz/sessions', json={'training_mode': 'new'}).json
        path = '/api/quiz/sessions/' + result['session_id']
        question = self.client.get(path + '/question/0')
        self.assertEqual(question.status_code, 200)
        self.client.post('/api/auth/logout')
        self.assertEqual(self.client.post('/api/auth/login', json={'password': 'merge-test-only'}).status_code, 200)
        self.assertEqual(self.client.get(path).status_code, 200)
        self.assertEqual(self.client.get(path + '/question/0').json, question.json)
        for _ in range(2):
            response = self.client.post(path + '/judge', json={'index': 0, 'answer': question.json['answer']})
            self.assertEqual(response.status_code, 200, response.json)
        self.assertEqual(self.client.get('/api/words/' + str(word['id'])).json['review_count'], 1)

    def test_revoked_login_and_registration_policy(self):
        other = a.app.test_client()
        self.assertEqual(other.get('/api/words').status_code, 401)
        self.assertEqual(other.post('/api/auth/register', json={'username': 'tester', 'password': 'merge-test-only'}).status_code, 403)
        self.assertEqual(self.client.put('/api/admin/policy', json={'registration': True}).status_code, 200)
        self.assertEqual(other.post('/api/auth/register', json={'username': 'tester', 'password': 'merge-test-only'}).status_code, 201)
        device = other.get('/api/devices').json[0]['id']
        self.assertEqual(other.delete('/api/devices/' + device).status_code, 200)
        self.assertEqual(other.get('/api/words').status_code, 401)

    def test_resumed_local_choice_keeps_option_order_and_grading(self):
        self.client.post('/api/words', json={'word': 'apple', 'chinese_meaning': '苹果'})
        session = self.client.post('/api/quiz/sessions', json={'training_mode': 'new'}).json
        path = '/api/quiz/sessions/' + session['session_id']
        old_options = ['a. 明亮的', '[n.] 苹果', 'int. 好啊', '名词：椅子']
        old_question = {'type': 'choice', 'mode': 'choice_en2cn', 'generation_source': 'local',
                        'options': old_options, 'answer': old_options[1]}
        with patch.object(a, 'make_question', return_value=old_question):
            self.assertEqual(self.client.get(path + '/question/0').json['options'], old_options)
        shown = self.client.get(path + '/question/0').json
        self.assertEqual(shown['options'], ['明亮的', '苹果', '好啊', '椅子'])
        result = self.client.post(path + '/judge', json={'index': 0, 'answer': shown['answer']})
        self.assertTrue(result.json['correct'])

    def test_model_keys_are_not_returned_and_local_lookup_works(self):
        response = self.client.put('/api/ai/providers', json={
            'providers': [{'id': 'test', 'base': 'https://example.invalid/v1', 'models': ['test'], 'key': 'private-test-value'}],
            'routes': {'general': {'provider': 'test', 'model': 'test'}}})
        self.assertEqual(response.status_code, 200, response.json)
        self.assertNotIn('private-test-value', json.dumps(self.client.get('/api/ai/providers').json))
        with patch.object(a, 'complete', side_effect=AssertionError('unexpected remote AI')):
            response = self.client.post('/api/words/lookup', json={'word': 'apple', 'enhance': False})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json['found'])

    def test_install_assets_and_agent_permissions(self):
        for path in ('/manifest.webmanifest', '/service-worker.js', '/static/features.js', '/static/icon-192.png'):
            response = self.client.get(path)
            self.assertEqual(response.status_code, 200, path)
            response.close()
        agent = a.app.test_client()
        headers = {'Authorization': 'Bearer ' + a.MCP_TOKEN}
        self.assertEqual(agent.get('/api/words', headers=headers).status_code, 200)
        self.assertEqual(agent.get('/api/admin/users', headers=headers).status_code, 403)

    def test_stale_chat_url_does_not_enable_chat_in_standalone_server(self):
        a.save_settings({'openwebui_url': '/'})
        with patch.dict(a.os.environ, {'BUNDLED_WEBUI': '', 'APP_URL_PREFIX': ''}):
            self.assertFalse(self.client.get('/api/settings').json['chat_enabled'])
        with patch.dict(a.os.environ, {'BUNDLED_WEBUI': '1', 'APP_URL_PREFIX': '/words'}):
            self.assertTrue(self.client.get('/api/settings').json['chat_enabled'])
        with patch.dict(a.os.environ, {'BUNDLED_WEBUI': '1', 'APP_URL_PREFIX': '/'}):
            self.assertFalse(self.client.get('/api/settings').json['chat_enabled'])


if __name__ == '__main__':
    unittest.main()
