import unittest
from unittest.mock import patch
from local_services import relevant_results, recent_articles, search_sync, search_terms

class SearchQualityTests(unittest.TestCase):
    def test_chinese_query_without_spaces_keeps_publisher(self):
        self.assertEqual(search_terms('浙江宣传最新文章'), ['浙江宣传'])

    def test_named_source_rejects_unrelated_and_does_not_pad(self):
        raw=[{'title':'无关娱乐新闻','href':'https://example.com/unrelated','body':'无关内容'},
             {'title':'浙江宣传丨新文章','href':'https://example.com/article','body':'浙江宣传 正文'}]
        result=relevant_results('浙江宣传 最新 文章',raw,8)
        self.assertEqual(len(result),1)
        self.assertEqual(result[0]['title'],'浙江宣传丨新文章')

    def test_english_query_keeps_specific_terms(self):
        result=relevant_results('Python documentation',[
            {'title':'Java manual','href':'https://example.com/java','body':'Java'},
            {'title':'Python documentation','href':'https://docs.python.org/','body':'Python'}],8)
        self.assertEqual(len(result),1)
        self.assertEqual(result[0]['link'],'https://docs.python.org/')

    def test_publisher_index_returns_dated_articles_in_order(self):
        html='''<ul><li>2026年10月30日<a href="/old.shtml">浙江宣传丨旧稿</a></li>
        <li>2026年10月31日<a href="/new.shtml">浙江宣传丨新稿</a></li>
        <li>2026年10月31日<a href="https://other.example/unrelated">浙江宣传丨外站稿</a></li></ul>'''
        with patch('local_services.urllib.request.urlopen') as open_url:
            open_url.return_value.__enter__.return_value.read.return_value=html.encode()
            result=recent_articles('浙江宣传 最新 文章',[
                {'title':'浙江宣传','link':'https://example.com/','snippet':'浙江宣传栏目'}],8)
        self.assertEqual([x['published_at'] for x in result],['2026-10-31','2026-10-30'])
        self.assertTrue(result[0]['link'].endswith('/new.shtml'))

    def test_no_matching_results_is_failure(self):
        with patch('local_services.urllib.request.urlopen',side_effect=OSError('offline')),patch.dict('sys.modules',{'ddgs':None}):
            with self.assertRaises(RuntimeError):search_sync('浙江宣传 最新 文章',8)

if __name__=='__main__':unittest.main()
