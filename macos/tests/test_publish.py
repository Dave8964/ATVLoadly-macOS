import hashlib,importlib.util,pathlib,tempfile,unittest
spec=importlib.util.spec_from_file_location('publisher',pathlib.Path(__file__).parents[1]/'publish-release.py')
p=importlib.util.module_from_spec(spec);spec.loader.exec_module(p)
class Publish(unittest.TestCase):
 def test_draft_is_found_without_a_published_git_tag(self):
  draft={'id':42,'tag_name':'macos-v0.7.3-candidate.4','draft':True}
  self.assertEqual(p.find_release([[],[draft]],draft['tag_name']),draft)
  self.assertIsNone(p.find_release([[draft]],'missing'))
 def test_incomplete_or_tampered_draft_is_rejected(self):
  with tempfile.TemporaryDirectory() as temp:
   root=pathlib.Path(temp);file=root/'app.zip';file.write_bytes(b'verified archive')
   asset={'name':file.name,'size':file.stat().st_size,'digest':'sha256:'+hashlib.sha256(file.read_bytes()).hexdigest()}
   self.assertEqual(p.verify_assets(root,[asset]),[file])
   with self.assertRaises(ValueError):p.verify_assets(root,[])
   file.write_bytes(b'tampered archive')
   with self.assertRaises(ValueError):p.verify_assets(root,[asset])
if __name__=='__main__':unittest.main()
