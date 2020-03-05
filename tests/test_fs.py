#!/usr/bin/python
import unittest
import os
import sys
from datetime import datetime
from swiftclient import client
from ftpcloudfs.fs import ObjectStorageFS, ListDirCache
from ftpcloudfs.errors import IOSError

import logging
logging.getLogger("swiftclient").setLevel(logging.CRITICAL)

class ObjectStorageFSTest(unittest.TestCase):
    '''ObjectStorageFS Tests'''

    def setUp(self):
        if not hasattr(self, 'username'):
            cls = self.__class__
            if not all(['OS_API_KEY' in os.environ,
                        'OS_API_USER' in os.environ,
                        'OS_AUTH_URL' in os.environ,
                        ]):
                print "env OS_API_USER/OS_API_KEY/OS_AUTH_URL not found."
                sys.exit(1)
            cls.username = os.environ.get('OS_API_USER')
            cls.api_key  = os.environ.get('OS_API_KEY')
            cls.auth_url = os.environ.get('OS_AUTH_URL')
            if 'OS_KEYSTONE_REGION_NAME' in os.environ:
                keystone = {'region_name'      : os.environ.get('OS_KEYSTONE_REGION_NAME'),
                            'tenant_separator' : os.environ.get('OS_KEYSTONE_TENANT_SEPARATOR', ':'),
                            'service_type'     : os.environ.get('OS_KEYSTONE_SERVICE_TYPE', 'object-store'),
                            'endpoint_type'    : os.environ.get('OS_KEYSTONE_ENDPOINT_TYPE', 'publicURL')}
                cls.cnx = ObjectStorageFS(self.username, self.api_key, self.auth_url, keystone)
                tenant_name, username = cls.username.split(keystone['tenant_separator'], 1)
                cls.conn = client.Connection(user=username, tenant_name=tenant_name,key=self.api_key, authurl=self.auth_url, auth_version='2.0')

            else:
                cls.cnx = ObjectStorageFS(self.username, self.api_key, self.auth_url)
                cls.conn = client.Connection(user=self.username, key=self.api_key, authurl=self.auth_url)
        self.container = "ftpcloudfs_testing"
        self.cnx.mkdir("/%s" % self.container)
        self.cnx.chdir("/%s" % self.container)
        self.large_object_container = self.container + "_segments"
        self.cnx.mkdir("/%s" % self.large_object_container)

    def create_file(self, path, contents):
        '''Create path with contents'''
        fd = self.cnx.open(path, "wb")
        fd.write(contents)
        fd.close()

    def create_file_with_split_limit(self, path, contents, split_size_in_mb):
        '''Create path with contents and split size'''
        fd = self.cnx.open(path, "wb")
        fd.__class__.split_size = split_size_in_mb * 10**6
        fd.write(contents)
        fd.close()

    def read_file(self, path):
        fd = self.cnx.open(path, "rb")
        contents = ''
        while True:
            chunk = fd.read()
            if not chunk:
                break
            contents += chunk
        fd.close()
        return contents

    def test_mkdir_chdir_rmdir(self):
        ''' mkdir/chdir/rmdir directory '''
        directory = "/foobarrandom"
        self.cnx.mkdir(directory)
        self.cnx.chdir(directory)
        self.assertEqual(self.cnx.getcwd(), directory)
        self.assertEqual(self.cnx.listdir(directory), [])
        self.cnx.rmdir(directory)

    def test_mkdir_chdir_mkdir_rmdir_subdir(self):
        ''' mkdir/chdir/rmdir sub directory '''
        directory = "/foobarrandom"
        self.cnx.mkdir(directory)
        self.cnx.chdir(directory)
        subdirectory = "potato"
        subdirpath = directory + "/" + subdirectory
        self.cnx.mkdir(subdirectory)
        # Can't delete a directory with stuff in
        self.assertRaises(EnvironmentError, self.cnx.rmdir, directory)
        self.cnx.chdir(subdirectory)
        self.cnx.chdir("..")
        self.assertEqual(self.cnx.getcwd(), directory)
        self.cnx.rmdir(subdirectory)
        self.cnx.chdir("..")
        self.cnx.rmdir(directory)

    def test_write_open_delete(self):
        ''' write/open/delete file '''
        content_string = "Hello Moto"
        self.create_file("testfile.txt", content_string)
        self.assertEquals(self.cnx.getsize("testfile.txt"), len(content_string))
        contents = self.read_file("testfile.txt")
        self.assertEqual(contents, content_string)
        self.cnx.remove("testfile.txt")

    def test_write_open_delete_subdir(self):
        ''' write/open/delete file in a subdirectory'''
        self.cnx.mkdir("potato")
        self.cnx.chdir("potato")
        content_string = "Hello Moto"
        self.create_file("testfile.txt", content_string)
        self.assertEquals(self.cnx.getsize("testfile.txt"), len(content_string))
        content = self.read_file("/%s/potato/testfile.txt" % self.container)
        self.assertEqual(content, content_string)
        self.cnx.remove("testfile.txt")
        self.cnx.chdir("..")
        self.cnx.rmdir("potato")

    def test_write_to_slash(self):
        ''' write to slash should not be permitted '''
        self.cnx.chdir("/")
        content_string = "Hello Moto"
        self.assertRaises(EnvironmentError, self.create_file, "testfile.txt", content_string)

    def test_chdir_to_a_file(self):
        ''' chdir to a file '''
        self.create_file("testfile.txt", "Hello Moto")
        self.assertRaises(EnvironmentError, self.cnx.chdir, "/%s/testfile.txt" % self.container)
        self.cnx.remove("testfile.txt")

    def test_chdir_to_slash(self):
        ''' chdir to slash '''
        self.cnx.chdir("/")

    def test_chdir_to_nonexistent_container(self):
        ''' chdir to non existent container'''
        self.assertRaises(EnvironmentError, self.cnx.chdir, "/i_dont_exist")

    def test_chdir_to_nonexistent_directory(self):
        ''' chdir to nonexistend directory'''
        self.assertRaises(EnvironmentError, self.cnx.chdir, "i_dont_exist")
        self.assertRaises(EnvironmentError, self.cnx.chdir, "/%s/i_dont_exist" % self.container)

    def test_listdir_root(self):
        ''' list root directory '''
        self.cnx.chdir("/")
        dt = abs(datetime.utcfromtimestamp(self.cnx.getmtime("/")) - datetime.utcnow())
        self.assertTrue(dt.seconds < 60)
        ls = self.cnx.listdir(".")
        self.assertTrue(self.container in ls)
        dt = abs(datetime.utcfromtimestamp(self.cnx.getmtime(self.container)) - datetime.utcnow())
        self.assertTrue(dt.seconds < 60)
        self.assertTrue('potato' not in ls)
        self.cnx.mkdir("potato")
        ls = self.cnx.listdir(".")
        self.assertTrue(self.container in ls)
        self.assertTrue('potato' in ls)
        self.cnx.rmdir("potato")

    def test_listdir(self):
        ''' list directory '''
        content_string = "Hello Moto"
        self.create_file("testfile.txt", content_string)
        dt = abs(datetime.utcfromtimestamp(self.cnx.getmtime("testfile.txt")) - datetime.utcnow())
        self.assertTrue(dt.seconds < 60)
        self.assertEqual(self.cnx.listdir("."), ["testfile.txt"])
        self.cnx.remove("testfile.txt")

    def test_listdir_subdir(self):
        ''' list a sub directory'''
        content_string = "Hello Moto"
        self.create_file("1.txt", content_string)
        self.create_file("2.txt", content_string)
        self.cnx.mkdir("potato")
        self.create_file("potato/3.txt", content_string)
        self.create_file("potato/4.txt", content_string)
        self.assertEqual(self.cnx.listdir("."), ["1.txt", "2.txt", "potato"])
        self.cnx.chdir("potato")
        self.assertEqual(self.cnx.listdir("."), ["3.txt", "4.txt"])
        self.cnx.remove("3.txt")
        self.cnx.remove("4.txt")
        self.assertEqual(self.cnx.listdir("."), [])
        self.cnx.chdir("..")
        self.cnx.remove("1.txt")
        self.cnx.remove("2.txt")
        self.assertEqual(self.cnx.listdir("."), ["potato"])
        dt = abs(datetime.utcfromtimestamp(self.cnx.getmtime("potato")) - datetime.utcnow())
        self.assertTrue(dt.seconds < 60)
        self.cnx.rmdir("potato")
        self.assertEqual(self.cnx.listdir("."), [])

    def test_rename_file(self):
        '''rename a file'''
        content_string = "Hello Moto" * 100
        self.create_file("testfile.txt", content_string)
        self.assertEquals(self.cnx.getsize("testfile.txt"), len(content_string))
        self.assertRaises(EnvironmentError, self.cnx.getsize, "testfile2.txt")
        self.cnx.rename("testfile.txt", "testfile2.txt")
        self.assertEquals(self.cnx.getsize("testfile2.txt"), len(content_string))
        self.assertRaises(EnvironmentError, self.cnx.getsize, "testfile.txt")
        self.cnx.remove("testfile2.txt")

    def test_rename_file_into_subdir1(self):
        '''rename a file into a subdirectory 1'''
        content_string = "Hello Moto"
        self.create_file("testfile.txt", content_string)
        self.cnx.mkdir("potato")
        self.assertEquals(self.cnx.getsize("testfile.txt"), len(content_string))
        self.assertRaises(EnvironmentError, self.cnx.getsize, "potato/testfile3.txt")
        self.cnx.rename("testfile.txt", "potato/testfile3.txt")
        self.assertEquals(self.cnx.getsize("potato/testfile3.txt"), len(content_string))
        self.assertRaises(EnvironmentError, self.cnx.getsize, "testfile.txt")
        self.cnx.remove("potato/testfile3.txt")
        self.cnx.rmdir("potato")

    def test_rename_file_into_subdir2(self):
        '''rename a file into a subdirectory without specifying dest leaf'''
        content_string = "Hello Moto"
        self.create_file("testfile.txt", content_string)
        self.cnx.mkdir("potato")
        self.assertEquals(self.cnx.getsize("testfile.txt"), len(content_string))
        self.assertRaises(EnvironmentError, self.cnx.getsize, "potato/testfile.txt")
        self.cnx.rename("testfile.txt", "potato")
        self.assertEquals(self.cnx.getsize("potato/testfile.txt"), len(content_string))
        self.assertRaises(EnvironmentError, self.cnx.getsize, "testfile.txt")
        self.cnx.remove("potato/testfile.txt")
        self.cnx.rmdir("potato")

    def test_rename_file_into_root(self):
        '''rename a file into a subdirectory without specifying dest leaf'''
        content_string = "Hello Moto"
        self.create_file("testfile.txt", content_string)
        self.assertRaises(EnvironmentError, self.cnx.rename, "testfile.txt", "/testfile.txt")
        self.cnx.remove("testfile.txt")

    def test_rename_directory_into_file(self):
        '''rename a directory into a file - shouldn't work'''
        content_string = "Hello Moto"
        self.create_file("testfile.txt", content_string)
        self.assertRaises(EnvironmentError, self.cnx.rename, "/%s" % self.container, "testfile.txt")
        self.cnx.remove("testfile.txt")

    def test_rename_directory_into_directory(self):
        '''rename a directory into a directory'''
        self.cnx.mkdir("potato")
        self.assertEquals(self.cnx.listdir("potato"), [])
        self.cnx.rename("potato", "potato2")
        self.assertEquals(self.cnx.listdir("potato2"), [])
        self.cnx.rmdir("potato2")

    def test_rename_directory_into_existing_directory(self):
        '''rename a directory into an existing directory'''
        self.cnx.mkdir("potato")
        self.cnx.mkdir("potato2")
        self.assertEquals(self.cnx.listdir("potato"), [])
        self.assertEquals(self.cnx.listdir("potato2"), [])
        self.cnx.rename("potato", "potato2")
        self.assertEquals(self.cnx.listdir("potato2"), ["potato"])
        self.assertEquals(self.cnx.listdir("potato2/potato"), [])
        self.cnx.rmdir("potato2/potato")
        self.cnx.rmdir("potato2")

    def test_rename_directory_into_self(self):
        '''rename a directory into itself'''
        self.cnx.mkdir("potato")
        self.assertEquals(self.cnx.listdir("potato"), [])
        self.cnx.rename("potato", "/%s" % self.container)
        self.assertEquals(self.cnx.listdir("potato"), [])
        self.cnx.rename("potato", "/%s/potato" % self.container)
        self.assertEquals(self.cnx.listdir("potato"), [])
        self.cnx.rename("potato", "potato")
        self.assertEquals(self.cnx.listdir("potato"), [])
        self.cnx.rename("/%s/potato" % self.container, ".")
        self.assertEquals(self.cnx.listdir("potato"), [])
        self.cnx.rmdir("potato")

    def test_rename_full_directory(self):
        '''rename a directory into a directory'''
        self.cnx.mkdir("potato")
        self.create_file("potato/something.txt", "p")
        try:
            self.assertEquals(self.cnx.listdir("potato"), ["something.txt"])
            self.assertRaises(EnvironmentError, self.cnx.rename, "potato", "potato2")
        finally:
            self.cnx.remove("potato/something.txt")
            self.cnx.rmdir("potato")

    def test_rename_container(self):
        '''rename an empty container'''
        self.cnx.mkdir("/potato")
        self.assertEquals(self.cnx.listdir("/potato"), [])
        self.assertRaises(EnvironmentError, self.cnx.listdir, "/potato2")
        self.cnx.rename("/potato", "/potato2")
        self.assertRaises(EnvironmentError, self.cnx.listdir, "/potato")
        self.assertEquals(self.cnx.listdir("/potato2"), [])
        self.cnx.rmdir("/potato2")

    def test_rename_full_container(self):
        '''rename a full container'''
        self.cnx.mkdir("/potato")
        self.create_file("/potato/test.txt", "onion")
        self.assertEquals(self.cnx.listdir("/potato"), ["test.txt"])
        self.assertRaises(EnvironmentError, self.cnx.rename, "/potato", "/potato2")
        self.cnx.remove("/potato/test.txt")
        self.cnx.rmdir("/potato")

    def test_unicode_file(self):
        '''Test unicode file creation'''
        # File names use a utf-8 interface
        file_name = u"Smiley\u263a.txt".encode("utf-8")
        self.create_file(file_name, "Hello Moto")
        self.assertEqual(self.cnx.listdir("."), [unicode(file_name, "utf-8")])
        self.cnx.remove(file_name)

    def test_unicode_directory(self):
        '''Test unicode directory creation'''
        # File names use a utf-8 interface
        dir_name = u"Smiley\u263aDir".encode("utf-8")
        self.cnx.mkdir(dir_name)
        self.assertEqual(self.cnx.listdir("."), [unicode(dir_name, "utf-8")])
        self.cnx.rmdir(dir_name)

    def test_mkdir_container_unicode(self):
        ''' mkdir/chdir/rmdir directory '''
        directory = u"/Smiley\u263aContainer".encode("utf-8")
        self.cnx.mkdir(directory)
        self.cnx.chdir(directory)
        self.cnx.rmdir(directory)

    def test_fakedir(self):
        '''Make some fake directories and test'''

        objs  = [ "test1.txt", "potato/test2.txt", "potato/sausage/test3.txt", "potato/sausage/test4.txt", ]
        for obj in objs:
            self.conn.put_object(self.container, obj, content_type="text/plain", contents="Hello Moto")

        self.assertEqual(self.cnx.listdir("."), ["potato", "test1.txt"])
        self.assertEqual(self.cnx.listdir("potato"), ["sausage","test2.txt"])
        self.assertEqual(self.cnx.listdir("potato/sausage"), ["test3.txt", "test4.txt"])

        self.cnx.chdir("potato")

        self.assertEqual(self.cnx.listdir("."), ["sausage","test2.txt"])
        self.assertEqual(self.cnx.listdir("sausage"), ["test3.txt", "test4.txt"])

        self.cnx.chdir("sausage")

        self.assertEqual(self.cnx.listdir("."), ["test3.txt", "test4.txt"])

        self.cnx.chdir("../..")

        for obj in objs:
            self.conn.delete_object(self.container, obj)

        self.assertEqual(self.cnx.listdir("."), [])

    def test_md5(self):
        self.conn.put_object(self.container, "test1.txt", content_type="text/plain", contents="Hello Moto")
        self.assertEquals(self.cnx.md5("test1.txt"),"0d933ae488fd55cc6bdeafffbaabf0c4")
        self.cnx.remove("test1.txt")
        self.assertRaises(EnvironmentError, self.cnx.md5, "/")
        self.assertRaises(EnvironmentError, self.cnx.md5, "/%s" % self.container)
        self.cnx.mkdir("/%s/sausage" % self.container)
        self.assertRaises(EnvironmentError, self.cnx.md5, "/%s/sausage" % self.container)
        self.cnx.rmdir("/%s/sausage" % self.container)

    def test_listdir_manifest(self):
        ''' list directory including a manifest file '''
        content_string = "0" * 1024
        for i in range(1, 5):
            self.create_file("testfile.part/%d" % i, content_string)
        self.conn.put_object(self.container, "testfile", contents=None, headers={ "x-object-manifest": '%s/testfile.part' % self.container })
        self.assertEqual(self.cnx.listdir("."), ["testfile", "testfile.part"])
        self.assertEqual(self.cnx.getsize("testfile"), 4096)
        self.cnx.remove("testfile")

    def test_listdir_manifest_same_name_as_segment_dir(self):
        ''' list directory including a manifest file '''
        content_string = "0" * 1024
        for i in range(1, 5):
            self.create_file("testfile/%d" % i, content_string)
        self.conn.put_object(self.container, "testfile", contents=None, headers={ "x-object-manifest": '%s/testfile' % self.container })
        self.assertEqual(self.cnx.listdir("."), ["testfile"])
        self.assertEqual(self.cnx.getsize("testfile"), 0)
        for i in range(1, 5):
            self.cnx.remove("testfile/%d" % i)
        self.cnx.remove("testfile") # magically becomes a file when the segments are deleted

    def test_seek_set_resume(self):
        ''' seek/resume functionality (seek_set) '''
        content_string = "This is a chunk of data"*1024
        self.create_file("testfile.txt", content_string)
        self.assertEquals(self.cnx.getsize("testfile.txt"), len(content_string))

        fd = self.cnx.open("testfile.txt", "rb")
        contents = fd.read(1024)
        fd.close()

        fd = self.cnx.open("testfile.txt", "rb")
        fd.seek(1024)
        contents += fd.read(512)
        fd.close()

        fd = self.cnx.open("testfile.txt", "rb")
        fd.seek(1024+512)
        contents += fd.read()
        fd.close()

        self.assertEqual(contents, content_string)
        self.cnx.remove("testfile.txt")

    def test_seek_end_resume(self):
        ''' seek/resume functionality (seek_end) '''
        content_string = "This is another chunk of data"*1024
        self.create_file("testfile.txt", content_string)
        self.assertEquals(self.cnx.getsize("testfile.txt"), len(content_string))

        fd = self.cnx.open("testfile.txt", "rb")
        contents = fd.read(len(content_string)-1024)
        fd.close()

        fd = self.cnx.open("testfile.txt", "rb")
        fd.seek(1024, 2)
        contents += fd.read()
        fd.close()

        self.assertEqual(contents, content_string)
        self.cnx.remove("testfile.txt")

    def test_seek_cur_resume(self):
        ''' seek/resume functionality (seek_cur) '''
        content_string = "This is another chunk of data"*1024
        self.create_file("testfile.txt", content_string)
        self.assertEquals(self.cnx.getsize("testfile.txt"), len(content_string))

        fd = self.cnx.open("testfile.txt", "rb")
        contents = fd.read(len(content_string)-1024)
        fd.close()

        fd = self.cnx.open("testfile.txt", "rb")
        fd.seek(1024)
        fd.read(512)
        fd.seek(len(content_string)-1024-512-1024, 1)
        contents += fd.read()
        fd.close()

        self.assertEqual(contents, content_string)
        self.cnx.remove("testfile.txt")

    def test_seek_invalid_offset(self):
        ''' seek functionality, invalid offset  '''
        content_string = "0"*1024
        self.create_file("testfile.txt", content_string)
        self.assertEquals(self.cnx.getsize("testfile.txt"), len(content_string))

        fd = self.cnx.open("testfile.txt", "rb")
        self.assertRaises(IOSError, fd.seek, 1025)
        fd.close()

        fd = self.cnx.open("testfile.txt", "rb")
        self.assertRaises(IOSError, fd.seek, -1)
        fd.close()

        fd = self.cnx.open("testfile.txt", "rb")
        self.assertRaises(IOSError, fd.seek, -1, 2)
        fd.close()

        fd = self.cnx.open("testfile.txt", "rb")
        self.assertRaises(IOSError, fd.seek, 1025, 2)
        fd.close()

        fd = self.cnx.open("testfile.txt", "rb")
        fd.read(512)
        self.assertRaises(IOSError, fd.seek, 513, 1)
        self.assertRaises(IOSError, fd.seek, -513, 1)
        fd.close()

        self.cnx.remove("testfile.txt")

    def test_large_file_support(self):
        ''' auto-split of large files '''
        size = 1024**2
        part_size = 64*1024
        fd = self.cnx.open("bigfile.txt", "wb")
        fd.split_size = part_size
        content = ''
        for part in xrange(size/4096):
            content += chr(part)*4096
            fd.write(chr(part)*4096)
        fd.close()
        self.assertEqual(self.cnx.listdir("."), ["bigfile.txt", "bigfile.txt.part"])
        self.assertEqual(self.cnx.getsize("bigfile.txt"), size)
        self.assertEqual(len(self.cnx.listdir("bigfile.txt.part/")), size/part_size)
        self.assertEqual(self.cnx.getsize("bigfile.txt.part/000000"), part_size)
        stored_content = self.read_file("/%s/bigfile.txt" % self.container)
        self.assertEqual(stored_content, content)
        self.cnx.remove("bigfile.txt")

    def test_large_file_support_name_encoding(self):
        ''' auto-split of large files '''
        size = 1024**2
        part_size = 64*1024
        file_name = u"bigfile & \u263a.txt"
        fd = self.cnx.open(file_name, "wb")
        fd.split_size = part_size
        content = ''
        for part in xrange(size/4096):
            content += chr(part)*4096
            fd.write(chr(part)*4096)
        fd.close()
        self.assertEqual(self.cnx.listdir("."), [file_name,
                                                 file_name + u".part",
                                                 ])
        self.assertEqual(self.cnx.getsize(file_name), size)
        self.cnx.remove(file_name)

    def test_large_file_support_big_chunk(self):
        ''' auto-split of large files, writing a single big chunk '''
        size = 1024**2
        part_size = 64*1024
        fd = self.cnx.open("bigfile.txt", "wb")
        fd.split_size = part_size
        fd.write('0'*size)
        fd.close()
        self.assertEqual(self.cnx.listdir("."), ["bigfile.txt", "bigfile.txt.part"])
        self.assertEqual(self.cnx.getsize("bigfile.txt"), size)
        self.assertEqual(len(self.cnx.listdir("bigfile.txt.part/")), size/part_size)
        self.assertEqual(self.cnx.getsize("bigfile.txt.part/000000"), part_size)
        self.cnx.remove("bigfile.txt")

    def test_large_file_support_content(self):
        ''' auto-split of large files, reminder last part '''
        size = 1024**2
        part_size = 64*1000 # size % part_size != 0
        content = ''
        fd = self.cnx.open("bigfile.txt", "wb")
        fd.split_size = part_size
        for part in xrange(size/4096):
            content += chr(part)*4096
            fd.write(chr(part)*4096)
        fd.close()
        stored_content = self.read_file("/%s/bigfile.txt" % self.container)
        self.assertEqual(len(stored_content), len(content))
        self.assertEqual(stored_content, content)
        self.cnx.remove("bigfile.txt")

    def test_large_file_rename(self):
        content_string = "x" * 6 * 1024 * 1024
        self.create_file_with_split_limit("testfile.txt", content_string, 5)
        self.assertEqual(len(self.read_file('testfile.txt')), len(content_string))
        self.cnx.rename("testfile.txt", "testfile2.txt")
        _, files = self.conn.get_container(self.container)
        #It's realy manifest
        self.assertEqual(self._search_file_by_name(files, 'testfile2.txt')['bytes'], 0)
        #And we can download whole file
        self.assertEqual(len(self.read_file('testfile2.txt')), len(content_string))
        self.cnx.remove("testfile.txt.part/000000")
        self.cnx.remove("testfile.txt.part/000001")
        self.cnx.remove("testfile2.txt")

    def test_large_file_remove(self):
      content_string = "x" * 6 * 1024 * 1024
      self.create_file_with_split_limit("testfile.txt", content_string, 5)
      self.assertEqual(self.cnx.listdir("."), ["testfile.txt", "testfile.txt.part"])
      self.cnx.remove('testfile.txt')
      self.assertEqual(self.cnx.listdir("."), [])

    def test_large_file_remove_fail(self):
      #Manualy delete .path folder. Expect not to fail.
      content_string = "x" * 6 * 1024 * 1024
      self.create_file_with_split_limit("testfile.txt", content_string, 5)
      self.assertEqual(self.cnx.listdir("."), ["testfile.txt", "testfile.txt.part"])
      self.cnx.remove("testfile.txt.part/000000")
      self.cnx.remove("testfile.txt.part/000001")
      self.assertEqual(self.cnx.listdir("."), ["testfile.txt"])
      self.cnx.remove('testfile.txt')
      self.assertEqual(self.cnx.listdir("."), [])

    def test_large_file_listing_hidden_parts(self):
      content_string = "x" * 6 * 1024 * 1024
      self.create_file_with_split_limit("testfile.txt", content_string, 5)
      self.assertEqual(self.cnx.listdir("."), ["testfile.txt", "testfile.txt.part"])
      self.cnx.hide_part_dir = True
      self.assertEqual(self.cnx.listdir("."), ["testfile.txt"])
      self.cnx.remove("testfile.txt.part/000000")
      self.cnx.remove("testfile.txt.part/000001")
      self.cnx.remove("testfile.txt")
      self.cnx.hide_part_dir = False

    def test_large_file_listing_hidden_parts_encoding(self):
      content_string = "x" * 6 * 1024 * 1024
      file_name = u"testfile & \u263a.txt".encode("utf-8")
      self.create_file_with_split_limit(file_name, content_string, 5)
      self.assertEqual(self.cnx.listdir("."), [unicode(file_name, "utf-8"),
                                               unicode(file_name, "utf-8") + u".part",
                                               ])
      self.cnx.hide_part_dir = True
      self.assertEqual(self.cnx.listdir("."), [unicode(file_name, "utf-8"),])
      self.cnx.remove(file_name)
      self.cnx.hide_part_dir = False

    def test_large_file_listing_hidden_parts_when_same_name_as_manifest(self):
        content_string = "0" * 1024
        for i in range(1, 5):
            self.create_file("testfile/%d" % i, content_string)
        self.conn.put_object(self.container, "testfile", contents=None, headers={ "x-object-manifest": '%s/testfile' % self.container })
        self.cnx.hide_part_dir = True
        self.assertEqual(self.cnx.listdir("."), ["testfile"])
        self.assertEqual(self.cnx.getsize("testfile"), 4096)
        self.cnx.remove("testfile")
        self.cnx.hide_part_dir = False
        self.assertEqual(self.cnx.listdir("."), [])

    def test_large_file_listing_hidden_parts_with_non_dir_segments(self):
        content_string = "0" * 1024
        for i in range(1, 5):
            self.create_file("testfile%d" % i, content_string)
        self.conn.put_object(self.container, "testfile", contents=None, headers={ "x-object-manifest": '%s/testfile' % self.container })
        self.cnx.hide_part_dir = True
        self.assertEqual(self.cnx.listdir("."), ["testfile"])
        self.assertEqual(self.cnx.getsize("testfile"), 4096)
        self.cnx.remove("testfile")
        for i in range(1, 5):
            self.cnx.remove("testfile%d" % i)
        self.cnx.hide_part_dir = False

    def test_large_file_listing_subdir_hidden_parts(self):
      content_string = "x" * 6 * 1024 * 1024
      self.cnx.mkdir("subdir")
      self.cnx.chdir("subdir")
      self.create_file_with_split_limit("testfile.txt", content_string, 5)
      self.assertEqual(self.cnx.listdir("."), ["testfile.txt", "testfile.txt.part"])
      self.cnx.hide_part_dir = True
      self.assertEqual(self.cnx.listdir("."), ["testfile.txt"])
      self.cnx.remove("testfile.txt.part/000000")
      self.cnx.remove("testfile.txt.part/000001")
      self.cnx.remove("testfile.txt")
      self.cnx.chdir("..")
      self.cnx.rmdir("subdir")
      self.cnx.hide_part_dir = False

    def test_large_file_remove_with_hidden_part(self):
      content_string = "x" * 6 * 1024 * 1024
      self.create_file_with_split_limit("testfile.txt", content_string, 5)
      self.assertEqual(self.cnx.listdir("."), ["testfile.txt", "testfile.txt.part"])
      self.cnx.hide_part_dir = True
      self.cnx.remove('testfile.txt')
      self.cnx.hide_part_dir = False
      #We realy delete hidden .part dir
      self.assertEqual(self.cnx.listdir("."), [])

    def test_large_file_rename_collision(self):
        content_string = "x" * 6 * 1024 * 1024
        content_string_2 = "y" * 6 * 1024 * 1024
        self.create_file_with_split_limit("testfile.txt", content_string, 5)
        self.assertEqual(len(self.read_file('testfile.txt')), len(content_string))
        self.cnx.rename("testfile.txt", "testfile2.txt")
        # upload the file again
        self.create_file_with_split_limit("testfile.txt", content_string_2, 5)
        # check the file is there
        self.assertEqual(self.read_file('testfile.txt'), content_string_2)
        self.cnx.remove("testfile.txt_01.part/000000")
        self.cnx.remove("testfile.txt_01.part/000001")
        self.cnx.remove("testfile.txt")
        # check we didn't change the old file
        self.assertEqual(self.read_file('testfile2.txt'), content_string)
        self.cnx.remove("testfile.txt.part/000000")
        self.cnx.remove("testfile.txt.part/000001")
        self.cnx.remove("testfile2.txt")

    def test_large_object_container_support(self):
        size = 1024**2
        part_size = 64*1024
        obj_name = "testfile.txt"
        fd = self.cnx.open(obj_name, "wb")
        fd.split_size = part_size
        fd.large_object_container = self.container + "_segments"
        content = ''
        for part in xrange(size/4096):
            content += chr(part)*4096
            fd.write(chr(part)*4096)
        fd.close()
        self.assertEqual(self.cnx.listdir("."), [obj_name])
        self.assertEqual(self.cnx.getsize(obj_name), size)
        self.assertEqual(self.cnx.listdir("/%s/" % fd.large_object_container), [obj_name])
        ts = self.cnx.listdir("/%s/%s" % (fd.large_object_container, obj_name))
        self.assertEqual(len(ts), 1)
        self.assertEqual(len(self.cnx.listdir("/%s/%s/%s/%s/" % (fd.large_object_container, obj_name, bytes(ts[0]), part_size))), size/part_size)
        self.assertEqual(self.cnx.getsize(obj_name), size)
        stored_content = self.read_file("/%s/%s" % (self.container, obj_name))
        self.assertEqual(stored_content, content)
        self.cnx.remove(obj_name)
        self.assertEqual(self.cnx.listdir("/%s/" % fd.large_object_container), [])

    def test_large_object_container_rename(self):
        size = 1024**2
        part_size = 64*1024
        fd = self.cnx.open("testfile.txt", "wb")
        fd.split_size = part_size
        fd.large_object_container = self.container + "_segments"
        content = ''
        for part in xrange(size/4096):
            content += chr(part)*4096
            fd.write(chr(part)*4096)
        fd.close()
        self.cnx.rename("testfile.txt", "testfile2.txt")
        _, objects = self.conn.get_container(self.container)
        self.assertEqual(self._search_file_by_name(objects, 'testfile2.txt')['bytes'], size)
        stored_content = self.read_file('testfile2.txt')
        self.assertEqual(stored_content, content)
        self.cnx.remove("testfile2.txt")

    def tearDown(self):
        for container in [self.container, self.large_object_container]:
            # Delete eveything from the container using the API
            _, fails = self.conn.get_container(container)
            for obj in fails:
                self.conn.delete_object(container, obj["name"])
            self.cnx.rmdir("/%s" % container)
            self.assertEquals(fails, [], "The test failed to clean up %s container after itself leaving these objects: %r" % (container, fails))

    def _search_file_by_name(self, container_files, file_name):
        file_list = [file for file in container_files if file['name'] == file_name]
        if len(file_list) == 0:
            raise ValueError("Cant find file %s in container_files %s" % (file_name, container_files))
        else:
            return file_list[0]

class MockupConnection(object):
    '''Mockup object to simulate a CF connection.'''
    def __init__(self, num_objects, objects):
        self.num_objects = num_objects
        self.objects = objects

    @staticmethod
    def gen_object(name):
        return dict(bytes=1024, content_type='text/plain',
                    hash='c644eacf6e9c21c7d2cca3ce8bb0ec13',
                    last_modified='2012-06-20T00:00:00.000000',
                    name=name)

    @staticmethod
    def gen_subdir(name):
        return dict(subdir=name)

    def list_containers_info(self):
        return [dict(count=self.num_objects, bytes=1024*self.num_objects, name='container'),]

    def get_account(self):
        return {}, [{ "name": "container", "count": self.num_objects, "bytes": self.num_objects*1024 },]

    def get_container(self, container, prefix=None, delimiter=None, marker=None, limit=10000):
        if container != 'container':
            raise client.ClientException("Not found", http_status=404)

        # test provided objects
        if self.objects:
            index = 0
            if marker:
                while True:
                    name = self.objects[index].get('name', self.objects[index].get('subdir'))
                    if marker == name.rstrip("/"):
                        index += 1
                        break
                    index += 1
                    if index == self.num_objects:
                        # marker not found, so it's ignored
                        index = 0
                        break
            return {}, self.objects[index:index+10000]

        # generated
        start = 0
        if marker:
            while start <= self.num_objects:
                if marker == 'object%s.txt' % start:
                    break
                start += 1

        end = self.num_objects-start
        if end == 0:
            # marker not found, so it's ingored (behaviour in OpenStack
            # Object Storage)
            start = 0
            end = self.num_objects
        if end > limit:
            end = limit

        return {}, [self.gen_object('object%s.txt' % i) for i in xrange(start, start+end)]

class MockupOSFS(object):
    '''Mockup object to simulate a CFFS.'''
    memcache_hosts = None
    auth_url = 'https://auth.service.fake/v1'
    username = 'user'
    hide_part_dir = False

    def __init__(self, num_objects, objects=None):
        if objects and len(objects) != num_objects:
            raise ValueError("objects provided but num_objects doesn't match")

        self.num_objects = num_objects
        self.objects = objects
        self.conn = MockupConnection(num_objects, objects)

    def _container_exists(self, container):
        if container != 'container':
            raise client.ClientException("Not found", http_status=404)

class ListDirTest(unittest.TestCase):
    '''
    ObjectStorageFS cache Tests.

    These tests use the Mockup* objects because some of the tests would require
    creating/deleting too many objects to run the test over the real storage.
    '''

    def test_listdir(self):
        """Test listdir, less than 10000 (limit) objects"""
        lc = ListDirCache(MockupOSFS(100))

        ld = lc.listdir('/')
        self.assertEqual(len(ld), 1)
        self.assertEqual(ld, ['container',])

        ld = lc.listdir('/container')
        self.assertEqual(len(ld), 100)
        self.assertEqual(sorted(ld), sorted(['object%s.txt' % i for i in xrange(100)]))

    def test_listdir_marker(self):
        """Test listdir, more than 10000 (limit) objects"""
        lc = ListDirCache(MockupOSFS(10100))

        ld = lc.listdir('/container')
        self.assertEqual(len(ld), 10100)
        self.assertEqual(sorted(ld), sorted(['object%s.txt' % i for i in xrange(10100)]))

    def test_listdir_marker_is_subdir(self):
        """Test listdir, more than 10000 (limit) objects, marker will be a subdir"""

        objects = [MockupConnection.gen_object("object%s.txt" % i) for i in xrange(9999)] + \
                  [MockupConnection.gen_subdir("00dir_name/")] + \
                  [MockupConnection.gen_object("object%s.txt" % i) for i in xrange(9999, 10099)]

        lc = ListDirCache(MockupOSFS(10100, objects))

        ld = sorted(lc.listdir('/container'))
        self.assertEqual(len(ld), 10100)
        self.assertEqual(ld[0], '00dir_name')
        self.assertEqual(ld[1:], sorted(['object%s.txt' % i for i in xrange(10099)]))

if __name__ == '__main__':
    unittest.main()
