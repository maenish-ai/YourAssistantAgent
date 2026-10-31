from pathlib import Path
import stat
import zipfile

import pytest

from yaa_lite.remote.files import RemoteFiles, FileError


@pytest.fixture
def files(tmp_path):
    area=tmp_path/'shared'; area.mkdir()
    (area/'reports').mkdir()
    (area/'report.txt').write_text('محتوى الملف', encoding='utf-8')
    return RemoteFiles(area)


def test_real_folder_copy_move_and_existing_destination_protection(files):
    created=files.create_folder('reports','نسخ')
    assert created['path']=='reports/نسخ'
    copied=files.copy_file('report.txt',created['path'],'new.txt')
    assert files.resolve(copied['path']).read_text()=='محتوى الملف'
    moved=files.move_file('report.txt','reports','moved.txt')
    assert not (files.root/'report.txt').exists()
    assert files.resolve(moved['path']).read_text()=='محتوى الملف'
    with pytest.raises(FileError): files.copy_file(moved['path'],'reports/نسخ','new.txt')
    with pytest.raises(FileError): files.move_file(moved['path'],'reports/نسخ','new.txt')
    assert files.resolve(moved['path']).exists()
    with pytest.raises(FileError): files.create_folder('reports','نسخ')


def test_cross_drive_paths_remain_scoped(tmp_path):
    drives={letter:tmp_path/letter for letter in ('C','D')}
    for path in drives.values():path.mkdir()
    (drives['C']/'source.txt').write_text('actual bytes')
    files=RemoteFiles(tmp_path, all_drives=True, roots=drives)
    result=files.move_file('@drives/C/source.txt','@drives/D','destination.txt')
    assert result['path']=='@drives/D/destination.txt'
    assert (drives['D']/'destination.txt').read_text()=='actual bytes'
    assert not (drives['C']/'source.txt').exists()
    with pytest.raises(FileError):files.create_folder('@drives/Z','folder')


@pytest.mark.parametrize('source,parent', [('report.txt','../outside'),('../outside/secret.txt','reports')])
def test_mutations_refuse_outside_scope(files,source,parent):
    with pytest.raises((FileError,FileNotFoundError)):files.copy_file(source,parent)


def test_symbolic_link_sources_and_destinations_cannot_redirect_mutations(files,tmp_path):
    outside=tmp_path/'outside';outside.mkdir();(outside/'secret.txt').write_text('untouched')
    try:
        (files.root/'redirect').symlink_to(outside,target_is_directory=True)
        (files.root/'inside-link').symlink_to(files.root/'reports',target_is_directory=True)
    except OSError:pytest.skip('Symlink unavailable')
    for folder in ('redirect','inside-link'):
        with pytest.raises(FileError):files.create_folder(folder,'new-folder')
    with pytest.raises(FileError):files.move_file('redirect/secret.txt','reports')
    assert (outside/'secret.txt').read_text()=='untouched'


def make_zip(files,names):
    path=files.root/'bundle.zip'
    with zipfile.ZipFile(path,'w') as output:
        for name,content in names:
            output.writestr(name,content)
    return path


def test_zip_extract_is_general_and_returns_observed_new_paths(files):
    make_zip(files,[('data/',b''),('data/readme.txt','hello'),('صور/notes.txt','عربي')])
    result=files.extract_zip('bundle.zip','reports','مشروع جديد')
    assert result['files']==2 and result['path']=='reports/مشروع جديد'
    assert files.resolve(result['path']+'/data/readme.txt').read_text()=='hello'
    assert files.resolve(result['path']+'/صور/notes.txt').read_text()=='عربي'
    assert (files.root/'bundle.zip').exists()
    with pytest.raises(FileError):files.extract_zip('bundle.zip','reports','مشروع جديد')
    assert not list((files.root/'reports').glob('.yaa-extract-*'))


@pytest.mark.parametrize('names',[
    [('../outside.txt','escape')], [('/absolute.txt','escape')], [('C:/escape.txt','escape')],
    [('folder\\escape.txt','escape')], [('folder/NUL.txt','bad')], [('folder/CON .txt','bad')],
    [('data/a.txt','one'),('DATA/b.txt','two')], [('same','one'),('same/child','two')],
    [('same.txt','one'),('SAME.TXT','two')],
])
def test_invalid_zip_publishes_nothing(files,names):
    make_zip(files,names)
    with pytest.raises(FileError):files.extract_zip('bundle.zip','reports','output')
    assert not (files.root/'reports'/'output').exists()
    assert not list((files.root/'reports').iterdir())


def test_zip_symbolic_links_and_size_limits_are_rejected(files,monkeypatch):
    info=zipfile.ZipInfo('redirect'); info.create_system=3
    info.external_attr=(stat.S_IFLNK|0o777)<<16
    make_zip(files,[(info,'../report.txt')])
    with pytest.raises(FileError):files.extract_zip('bundle.zip','reports','output')
    make_zip(files,[('readme.txt','actual data')])
    monkeypatch.setattr('yaa_lite.remote.files.MAX_ZIP_UNPACKED',3)
    with pytest.raises(FileError):files.extract_zip('bundle.zip','reports','output')
    assert not list((files.root/'reports').iterdir())


def test_move_preserves_changed_source_and_copied_bytes(files,monkeypatch):
    original=files.import_file
    def copy_then_source_changed(source,folder,name):
        result=original(source,folder,name)
        Path(source).write_text('changed during copy')
        return result
    monkeypatch.setattr(files,'import_file',copy_then_source_changed)
    with pytest.raises(FileError,match='تغيّر المصدر'):files.move_file('report.txt','reports','copied.txt')
    assert (files.root/'report.txt').read_text()=='changed during copy'
    assert (files.root/'reports/copied.txt').read_text()=='محتوى الملف'
