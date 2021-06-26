# -*- mode: python ; coding: utf-8 -*-

block_cipher = None


a = Analysis(['WordMapper.py'],
             pathex=['E:\\labsoftwares\\NewBuild6.0'],
             binaries=[],
             datas=[('working\\','working'),('C:\\Users\\jxa421\\AppData\\Local\\Continuum\\anaconda3\\envs\\WordMapper_legacy\\Lib\\site-packages\\osgeo\\data\\proj\\*','osgeo/data/proj')],
             hiddenimports=['pkg_resources.py2_warn'],
             hookspath=[],
             runtime_hooks=[],
             excludes=[],
             win_no_prefer_redirects=False,
             win_private_assemblies=False,
             cipher=block_cipher,
             noarchive=False)
pyz = PYZ(a.pure, a.zipped_data,
             cipher=block_cipher)
exe = EXE(pyz,
          a.scripts,
          [],
          exclude_binaries=True,
          name='WordMapper',
          debug=False,
          bootloader_ignore_signals=False,
          strip=False,
          upx=True,
          console=True )
coll = COLLECT(exe,
               a.binaries,
               a.zipfiles,
               a.datas,
               strip=False,
               upx=True,
               upx_exclude=[],
               name='WordMapper')
