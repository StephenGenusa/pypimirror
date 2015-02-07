import os
import sys
import time
import datetime
import tarfile
import gzip
import zipfile

only_test_validity_of_archive = False

# From http://code.activestate.com/recipes/410692/
class switch(object):
    def __init__(self, value):
        self.value = value
        self.fall = False

    def __iter__(self):
        """Return the match method once, then stop"""
        yield self.match
        raise StopIteration
    
    def match(self, *args):
        """Indicate whether or not to enter a case suite"""
        if self.fall or not args:
            return True
        elif self.value in args: # changed for v1.5, see below
            self.fall = True
            return True
        else:
            return False

# From http://stackoverflow.com/questions/16976192/whats-the-way-to-extract-file-extension-from-file-name-in-python
def splitext(path):
    for ext in ['.tar.gz', '.tar.bz2']:
        if path.endswith(ext):
            return path[:-len(ext)], path[-len(ext):]
    return os.path.splitext(path)


def touch_file(file_name, mod_time):
    try:
        if not only_test_validity_of_archive :
            if mod_time > 0 and mod_time < 1609376461:
                os.utime(file_name, ((mod_time,mod_time)))
        #else:
        #    open("file_errors.txt", 'a').writelines(file_name+ ' has invalid datetime in file\n')
    except:
        pass


def get_time_for_tarfile(file_name):
    newest_time = 0
    try:
        with tarfile.TarFile.open(file_name, 'r') as tarredFile:
            members = tarredFile.getmembers()
            if not only_test_validity_of_archive :
                for member in members:
                    if member.mtime > newest_time:
                        newest_time = member.mtime
    except:
        open("file_errors.txt", 'a').writelines(file_name+'\n')
    return newest_time
    
def get_time_for_zipfile(file_name):
    newest_time = 0
    try:
        with zipfile.ZipFile(file_name, 'r') as zippedFile:
            members = zippedFile.infolist()
            if not only_test_validity_of_archive :
                for member in members:
                    #print member.orig_filename            
                    curDT = time.mktime(datetime.datetime(*member.date_time).timetuple())
                    if curDT > newest_time:
                        newest_time = curDT
    except:
        open("file_errors.txt", 'a').writelines(file_name + '\n')
    return newest_time


def process_file(filename_to_process, verbose):
    if os.path.getsize(filename_to_process) > 0:
        filename, file_extension = splitext(filename_to_process)
        for case in switch(file_extension.lower()):
            if case('.zip'):
                if verbose: print "    " + filename_to_process
                touch_file(filename_to_process, get_time_for_zipfile(filename_to_process))
                break
            if case('.whl'):
                if verbose: print "    " + filename_to_process
                touch_file(filename_to_process, get_time_for_zipfile(filename_to_process))
                break
            if case('.egg'):
                if verbose: print "    " + filename_to_process
                touch_file(filename_to_process, get_time_for_zipfile(filename_to_process))
                break
            if case('.tar'):
                if verbose: print "    " + filename_to_process
                touch_file(filename_to_process, get_time_for_tarfile(filename_to_process))
                break
            if case('.tar.gz'):
                if verbose: print "    " + filename_to_process
                touch_file(filename_to_process, get_time_for_tarfile(filename_to_process))
                break
            if case('.tar.bz2'):
                if verbose: print "    " + filename_to_process
                touch_file(filename_to_process, get_time_for_tarfile(filename_to_process))
                break
            if case(''):
                break
            if case('.html'):
                break
            if case('.htm'):
                break
            if case('.txt'):
                break
            if case('.py'):
                break
            if case('.md5'):
                break
            if case(''): # default, could also just omit condition or 'if True'
                print "Extension '" + file_extension.lower() + "' not handled."
    else:
        open("file_errors.txt", 'a').writelines('(empty file) ' + filename_to_process + '\n')
        


def main(root_path):
    for root, dirs, files in os.walk(root_path):
        print 'Processing Path ' + root
        for file in files:
            process_file(root + "/" + file, False)
    print "\nStephen's Archive Re-Touch Utility Complete\n"




if __name__ == "__main__":
    main(root_path='/Volumes/Python')
