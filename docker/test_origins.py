import ast
from pathlib import Path
import unittest

class OriginTests(unittest.TestCase):
    def test_both_launchers_accept_loopback_aliases_only_locally(self):
        for filename in ('entrypoint.py','local_chat_entrypoint.py'):
            tree=ast.parse(Path(__file__).with_name(filename).read_text())
            function=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='local_origins')
            namespace={};exec(compile(ast.Module(body=[function],type_ignores=[]),filename,'exec'),namespace)
            origins=namespace['local_origins']
            self.assertEqual(set(origins('http://localhost:5050').split(';')),{'http://127.0.0.1:5050','http://localhost:5050'})
            self.assertEqual(origins('https://words.example.com'),'https://words.example.com')

if __name__=='__main__':unittest.main()
