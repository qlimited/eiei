from odoo import api, fields, models
from odoo.modules.module import get_module_resource
from odoo.exceptions import ValidationError

import zipfile
import os
import base64


class Module(models.Model):
    _inherit = 'ir.module.module'

    module_file = fields.Binary()
    module_filename = fields.Char()

    def button_get_binary(self):
        path = get_module_resource(self.name)
        path = path.replace('/' + self.name, '')
        print(path)
        base = get_module_resource('base_module')
        module_name = base.replace('base_module', self.name)
        self.zip_directory(path, module_name + '.zip')
        file = open(module_name + '.zip', "rb")
        out = file.read()
        self.module_file = base64.b64encode(out)
        self.module_filename = f'{self.name}.zip'
        os.unlink(module_name + '.zip')

    def zip_directory(self, folder_path, zip_path):
        with zipfile.ZipFile(zip_path, mode='w') as zipf:
            len_dir_path = len(folder_path)
            for root, _, files in os.walk(folder_path):
                for file in files:
                    file_path = os.path.join(root, file)
                    zipf.write(file_path, file_path[len_dir_path:])
