
import os
import unittest
from main import app
from database import get_db_connection

class TestExcelImport(unittest.TestCase):
    def setUp(self):
        self.app = app.test_client()
        self.app.testing = True
        # Ensure output dir exists
        if not os.path.exists('output'):
            os.makedirs('output')

    def test_import_route_get(self):
        response = self.app.get('/excelimport')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Import Users from Excel', response.data)

    def test_import_process(self):
        # We assume testdata.xlsx exists as per prompt.
        if not os.path.exists('testdata.xlsx'):
            print("Skipping import test: testdata.xlsx not found.")
            return

        with open('testdata.xlsx', 'rb') as f:
            data = {
                'file': (f, 'testdata.xlsx')
            }
            response = self.app.post('/excelimport', data=data, content_type='multipart/form-data', follow_redirects=True)
            self.assertEqual(response.status_code, 200)
            self.assertIn(b'Import Summary', response.data)
            
            # Verify DB (Check one user if we know the content, or just check count increased)
            # Actually, let's check PDF generation.
            # Assuming the excel creates at least one user.
            pdfs = [f for f in os.listdir('output') if f.endswith('.pdf')]
            self.assertTrue(len(pdfs) > 0, "No PDFs generated in output/")

if __name__ == '__main__':
    unittest.main()
