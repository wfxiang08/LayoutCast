# -*- coding:utf-8 -*-
#!/usr/bin/python
__author__ = 'mmin18'
__version__ = '1.50922'
__plugin__ = '1'

from subprocess import Popen, PIPE, check_call
from distutils.version import LooseVersion
import argparse
import sys
import os
import io
import re
import time
import shutil
import json
import zipfile


# http://stackoverflow.com/questions/377017/test-if-executable-exists-in-python
def is_exe(fpath):
    return os.path.isfile(fpath) and os.access(fpath, os.X_OK)


def which(program):
    import os

    fpath, fname = os.path.split(program)
    if fpath:
        if is_exe(program):
            return program
    else:
        for path in os.environ["PATH"].split(os.pathsep):
            path = path.strip('"')
            exe_file = os.path.join(path, program)
            if is_exe(exe_file):
                return exe_file

    return None


def cexec_fail_exit(args, code, stdout, stderr):
    if code != 0:
        print('Fail to exec %s' % args)
        print(stdout)
        print(stderr)
        exit(code)


def cexec(args, callback=cexec_fail_exit, addPath=None, exitcode=1):
    env = None
    if addPath:
        import copy

        env = copy.copy(os.environ)
        env['PATH'] = addPath + os.path.pathsep + env['PATH']
    p = Popen(args, stdin=PIPE, stdout=PIPE, stderr=PIPE, env=env)
    output, err = p.communicate()
    code = p.returncode
    if code and exitcode:
        code = exitcode
    if callback:
        callback(args, code, output, err)
    return output


def curl(url, body=None, ignoreError=False, exitcode=1):
    print ("URL: ", url)
    import sys

    try:
        if sys.version_info >= (3, 0):
            import urllib.request

            return urllib.request.urlopen(url, data=body).read().decode('utf-8').strip()
        else:
            import urllib2

            return urllib2.urlopen(url, data=body).read().decode('utf-8').strip()
    except Exception as e:
        if ignoreError:
            return None
        else:
            print(e)
            exit(exitcode)


def open_as_text(path):
    if not path or not os.path.isfile(path):
        return ''
    with io.open(path, 'r', errors='replace') as f:
        data = f.read()
        return data
    print('fail to open %s' % path)
    return ''


def is_gradle_project(dir):
    return os.path.isfile(os.path.join(dir, 'build.gradle'))


def parse_properties(path):
    return os.path.isfile(path) and dict(line.strip().split('=') for line in open(path) if
                                         ('=' in line and not line.startswith('#'))) or {}


def balanced_braces(arg):
    if '{' not in arg:
        return ''
    chars = []
    n = 0
    for c in arg:
        if c == '{':
            if n > 0:
                chars.append(c)
            n += 1
        elif c == '}':
            n -= 1
            if n > 0:
                chars.append(c)
            elif n == 0:
                return ''.join(chars).lstrip().rstrip()
        elif n > 0:
            chars.append(c)
    return ''


def remove_comments(str):
    # remove comments in groovy
    return re.sub(r'''(/\*([^*]|[\r\n]|(\*+([^*/]|[\r\n])))*\*+/)|(//.*)''', '', str)


def __deps_list_eclipse(list, project):
    prop = parse_properties(os.path.join(project, 'project.properties'))
    for i in range(1, 100):
        dep = prop.get('android.library.reference.%d' % i)
        if dep:
            absdep = os.path.abspath(os.path.join(project, dep))
            __deps_list_eclipse(list, absdep)
            if not absdep in list:
                list.append(absdep)


#
def __deps_list_gradle(list, project):
    str = open_as_text(os.path.join(project, 'build.gradle'))
    str = remove_comments(str)
    ideps = []

    # for depends in re.findall(r'dependencies\s*\{.*?\}', str, re.DOTALL | re.MULTILINE):
    # 1. 获取项目内的依赖
    for m in re.finditer(r'dependencies\s*\{', str):
        depends = balanced_braces(str[m.start():])
        for proj in re.findall(r'''compile\s+project\s*\(.*['"]:(.+)['"].*\)''', depends):
            ideps.append(proj.replace(':', os.path.sep))
    if len(ideps) == 0:
        return

    path = project
    for i in range(1, 3):
        # 这是什么意思?
        # /xxx/path0/path1/path2/
        # /xxx/path0/path1/path2/..
        # /xxx/path0/path1/path2/../..
        path = os.path.abspath(os.path.join(path, os.path.pardir))
        b = True
        deps = []
        for idep in ideps:
            # 定位: deps
            dep = os.path.join(path, idep)
            if not os.path.isdir(dep):
                b = False
                break
            deps.append(dep)

        # 如果有: deps, 如何处理呢?
        if b:
            for dep in deps:
                __deps_list_gradle(list, dep)
                if not dep in list:
                    list.append(dep)
            break


def deps_list(dir):
    if is_gradle_project(dir):
        list = []
        __deps_list_gradle(list, dir)
        return list
    else:
        list = []
        __deps_list_eclipse(list, dir)
        return list


def manifestpath(dir):
    # Android项目的布局
    # 要么在跟目录下有啥，要么在: src/main目录下有啥
    if os.path.isfile(os.path.join(dir, 'AndroidManifest.xml')):
        return os.path.join(dir, 'AndroidManifest.xml')
    if os.path.isfile(os.path.join(dir, 'src', 'main', 'AndroidManifest.xml')):
        return os.path.join(dir, 'src', 'main', 'AndroidManifest.xml')


def package_name(dir):
    # 1. 获取AndroidManifest.xml文件
    path = manifestpath(dir)
    data = open_as_text(path)

    # 2. 判断是否存在: package=
    #    可能AndroidManifest为空?
    for pn in re.findall('package=\"([\w\d_\.]+)\"', data):
        return pn


def get_apk_path(dir):
    # 获取最新的apk
    # apk的路径:
    # bin/*.apk
    # build/outputs/apk/*.apk
    #
    if not is_gradle_project(dir):
        apkpath = os.path.join(dir, 'bin')
    else:
        apkpath = os.path.join(dir, 'build', 'outputs', 'apk')


    # Get the lastmodified *.apk file
    maxt = 0
    maxd = None
    for dirpath, dirnames, files in os.walk(apkpath):
        for fn in files:
            if fn.endswith('.apk') and not fn.endswith('-unaligned.apk') and not fn.endswith('-unsigned.apk'):
                lastModified = os.path.getmtime(os.path.join(dirpath, fn))
                if lastModified > maxt:
                    maxt = lastModified
                    maxd = os.path.join(dirpath, fn)
    return maxd


def package_name_fromapk(dir, sdkdir):
    # Get the package name from maxd
    aaptpath = get_aapt(sdkdir)
    if aaptpath:
        apkpath = get_apk_path(dir)
        if apkpath:
            # 通过: aapt来操作
            aaptargs = [aaptpath, 'dump', 'badging', apkpath]
            output = cexec(aaptargs, callback=None)

            for pn in re.findall('package: name=\'([^\']+)\'', output):
                return pn
    return package_name(dir)


def get_latest_packagename(dirlist, sdkdir):
    maxt = 0
    maxd = None
    for dir in dirlist:
        if dir:
            # 这个是什么意思呢?
            # 是不是最终只有一个apk是签名的呢?
            apkfile = get_apk_path(dir)
            if apkfile:
                lastModified = os.path.getmtime(apkfile)
                if lastModified > maxt:
                    maxt = lastModified
                    maxd = dir
    if maxd:
        return package_name_fromapk(maxd, sdkdir)


def isResName(name):
    if name == 'drawable' or name.startswith('drawable-'):
        return 2
    if name == 'layout' or name.startswith('layout-'):
        return 2
    if name == 'values' or name.startswith('values-'):
        return 2
    if name == 'anim' or name.startswith('anim-'):
        return 1
    if name == 'color' or name.startswith('color-'):
        return 1
    if name == 'menu' or name.startswith('menu-'):
        return 1
    if name == 'raw' or name.startswith('raw-'):
        return 1
    if name == 'xml' or name.startswith('xml-'):
        return 1
    if name == 'mipmap' or name.startswith('mipmap-'):
        return 1
    if name == 'animator' or name.startswith('animator-'):
        return 1
    return 0


def countResDir(dir):
    c = 0
    d = 0
    if os.path.isdir(dir):
        for subd in os.listdir(dir):
            v = isResName(subd)
            if v > 1:
                d += 1
            if v > 0:
                c += 1
    if d == 0:
        return 0
    return c


def countAssetDir(dir):
    a = 0
    if os.path.isdir(dir):
        for subd in os.listdir(dir):
            if not subd.startswith('.'):
                a += 1
    return a


def resdir(dir):
    dir1 = os.path.join(dir, 'res')
    dir2 = os.path.join(dir, 'src', 'main', 'res')
    a = countResDir(dir1)
    b = countResDir(dir2)
    if b == 0 and a == 0:
        return None
    elif b > a:
        return dir2
    else:
        return dir1


def assetdir(dir):
    # 注意项目的组织形式:
    # asserts
    # src/main/asserts
    dir1 = os.path.join(dir, 'assets')
    dir2 = os.path.join(dir, 'src', 'main', 'assets')
    a = countAssetDir(dir1)
    b = countAssetDir(dir2)
    if b == 0 and a == 0:
        return None
    elif b > a:
        return dir2
    else:
        return dir1


def get_asset_from_apk(apk_filename, dest_dir):
    with zipfile.ZipFile(apk_filename) as zf:
        for member in zf.infolist():
            path = dest_dir
            if member.filename.startswith('assets/'):
                zf.extract(member, path)


def countSrcDir2(dir, lastBuild=0, list=None):
    count = 0
    lastModified = 0
    for dirpath, dirnames, files in os.walk(dir):
        if re.findall(r'[/\\+]androidTest[/\\+]', dirpath) or '/.' in dirpath:
            continue
        for fn in files:
            if fn.endswith('.java'):
                count += 1
                mt = os.path.getmtime(os.path.join(dirpath, fn))
                lastModified = max(lastModified, mt)
                if list != None and mt > lastBuild:
                    list.append(os.path.join(dirpath, fn))
    return (count, lastModified)


def srcdir2(dir, lastBuild=0, list=None):
    for srcdir in [os.path.join(dir, 'src', 'main', 'java'), os.path.join(dir, 'src')]:
        olist = None
        if list != None:
            olist = []

        # 返回源代码的文件数&最后修改时间
        (count, lastModified) = countSrcDir2(srcdir, lastBuild=lastBuild, list=olist)
        if count > 0:
            if list != None:
                list.extend(olist)
            return (srcdir, count, lastModified)
    return (None, 0, 0)


def libdir(dir):
    ddir = os.path.join(dir, 'libs')
    if os.path.isdir(ddir):
        return ddir
    else:
        return None


def is_launchable_project(dir):
    if is_gradle_project(dir):
        data = open_as_text(os.path.join(dir, 'build.gradle'))
        data = remove_comments(data)
        if re.findall(r'''apply\s+plugin:\s*['"]com.android.application['"]''', data, re.MULTILINE):
            return True
    elif os.path.isfile(os.path.join(dir, 'project.properties')):
        data = open_as_text(os.path.join(dir, 'project.properties'))
        if re.findall(r'''^\s*target\s*=.*$''', data, re.MULTILINE) and not re.findall(
                r'''^\s*android.library\s*=\s*true\s*$''', data, re.MULTILINE):
            return True
    return False


def __append_project(list, dir, depth):
    if package_name(dir):
        list.append(dir)
    elif depth > 0:
        for cname in os.listdir(dir):
            if cname == 'build' or cname == 'bin':
                continue
            cdir = os.path.join(dir, cname)
            if os.path.isdir(cdir):
                __append_project(list, cdir, depth - 1)


def list_projects(dir):
    list = []
    if os.path.isfile(os.path.join(dir, 'settings.gradle')):
        data = open_as_text(os.path.join(dir, 'settings.gradle'))

        # 找出所有的 include pattern
        for line in re.findall(r'''include\s*(.+)''', data):
            # 找出所有的project
            for proj in re.findall(r'''[\s,]+['"](.*?)['"]''', ',' + line):
                # include ":library:common" --> library/common
                # include "library" ?
                dproj = (proj.startswith(':') and proj[1:] or proj).replace(':', os.path.sep)
                cdir = os.path.join(dir, dproj)
                if package_name(cdir):
                    list.append(cdir)
    else:
        __append_project(list, dir, 2)
    return list


def list_aar_projects(dir, deps):
    pnlist = [package_name(i) for i in deps]
    pnlist.append(package_name(dir))
    list1 = []
    if os.path.isdir(os.path.join(dir, 'build', 'intermediates', 'incremental', 'mergeResources')):
        for dirpath, dirnames, files in os.walk(
                os.path.join(dir, 'build', 'intermediates', 'incremental', 'mergeResources')):
            if re.findall(r'[/\\+]androidTest[/\\+]', dirpath):
                continue
            for fn in files:
                if fn == 'merger.xml':
                    data = open_as_text(os.path.join(dirpath, fn))
                    for s in re.findall(r'''path="([^"]+)"''', data):
                        (parent, child) = os.path.split(s)
                        if child.endswith('.xml') or child.endswith('.png') or child.endswith(
                                '.jpg'):
                            (parent, child) = os.path.split(parent)
                            if isResName(child) and not parent in list1:
                                list1.append(parent)
                        elif os.path.isdir(s) and not s in list1 and countResDir(s) > 0:
                            list1.append(s)
    list2 = []
    for ppath in list1:
        parpath = os.path.abspath(os.path.join(ppath, os.pardir))
        pn = package_name(parpath)
        if pn and not pn in pnlist:
            list2.append(ppath)
    return list2


# 获取android.jar文件的路径
def get_android_jar(path):
    if not os.path.isdir(path):
        return None
    platforms = os.path.join(path, 'platforms')
    if not os.path.isdir(platforms):
        return None
    api = 0
    result = None
    for pd in os.listdir(platforms):
        pd = os.path.join(platforms, pd)
        if os.path.isdir(pd) and os.path.isfile(
                os.path.join(pd, 'source.properties')) and os.path.isfile(
            os.path.join(pd, 'android.jar')):
            s = open_as_text(os.path.join(pd, 'source.properties'))
            m = re.search(r'^AndroidVersion.ApiLevel\s*[=:]\s*(.*)$', s, re.MULTILINE)
            if m:
                a = int(m.group(1))
                if a > api:
                    api = a
                    result = os.path.join(pd, 'android.jar')
    return result


def get_adb(path):
    execname = os.name == 'nt' and 'adb.exe' or 'adb'
    if os.path.isdir(path) and is_exe(os.path.join(path, 'platform-tools', execname)):
        return os.path.join(path, 'platform-tools', execname)


def get_aapt(path):
    # 首先获取: execname
    execname = os.name == 'nt' and 'aapt.exe' or 'aapt'
    # 给定sdk path
    if os.path.isdir(path) and os.path.isdir(os.path.join(path, 'build-tools')):
        btpath = os.path.join(path, 'build-tools')

        # 实现版本号比较
        minv = LooseVersion('0')
        minp = None
        for pn in os.listdir(btpath):
            if is_exe(os.path.join(btpath, pn, execname)):
                if LooseVersion(pn) > minv:
                    minv = LooseVersion(pn)
                    minp = os.path.join(btpath, pn, execname)
        return minp


def get_dx(path):
    # dx的作用
    execname = os.name == 'nt' and 'dx.bat' or 'dx'
    if os.path.isdir(path) and os.path.isdir(os.path.join(path, 'build-tools')):
        btpath = os.path.join(path, 'build-tools')
        minv = LooseVersion('0')
        minp = None
        for pn in os.listdir(btpath):
            if is_exe(os.path.join(btpath, pn, execname)):
                if LooseVersion(pn) > minv:
                    minv = LooseVersion(pn)
                    minp = os.path.join(btpath, pn, execname)
        return minp


def get_android_sdk(dir, condf=get_android_jar):
    # 如何获取Android SDK
    # 1. local.properties --> sdk.dir
    # 2. ANDROID_HOME/ANDROID_SDK
    # 3. 其他: ~/Library/Android/sdk
    #
    s = open_as_text(os.path.join(dir, 'local.properties'))
    m = re.search(r'^sdk.dir\s*[=:]\s*(.*)$', s, re.MULTILINE)
    if m:
        val = m.group(1).replace('\\:', ':').replace('\\=', '=').replace('\\\\', '\\')
        if os.path.isdir(val) and condf(val):
            return val

    path = os.getenv('ANDROID_HOME')
    if path and os.path.isdir(path) and condf(path):
        return path

    path = os.getenv('ANDROID_SDK')
    if path and os.path.isdir(path) and condf(path):
        return path

    # mac
    path = os.path.expanduser('~/Library/Android/sdk')
    if path and os.path.isdir(path) and condf(path):
        return path

    # windows
    path = os.path.expanduser('~/AppData/Local/Android/sdk')
    if path and os.path.isdir(path) and condf(path):
        return path


def get_javac(dir):
    # 如何获取JavaC
    execname = os.name == 'nt' and 'javac.exe' or 'javac'
    if dir and os.path.isfile(os.path.join(dir, 'bin', execname)):
        return os.path.join(dir, 'bin', execname)

    wpath = which(execname)
    if wpath:
        return wpath

    path = os.getenv('JAVA_HOME')
    if path and is_exe(os.path.join(path, 'bin', execname)):
        return os.path.join(path, 'bin', execname)

    if os.name == 'nt':
        btpath = 'C:\\Program Files\\Java'
        if os.path.isdir(btpath):
            minv = ''
            minp = None
            for pn in os.listdir(btpath):
                path = os.path.join(btpath, pn, 'bin', execname)
                if is_exe(path):
                    if pn > minv:
                        minv = pn
                        minp = path
            return minp
    else:
        # 如果没有指定，则在默认的路径下搜索
        for btpath in ['/Library/Java/JavaVirtualMachines',
                       '/System/Library/Java/JavaVirtualMachines']:
            if os.path.isdir(btpath):
                minv = ''
                minp = None
                for pn in os.listdir(btpath):
                    path = os.path.join(btpath, pn, 'Contents', 'Home', 'bin', execname)
                    if is_exe(path):
                        if pn > minv:
                            minv = pn
                            minp = path
                if minp:
                    return minp


def search_path(dir, filename):
    dir0 = filename
    if os.path.sep in filename:
        dir0 = filename[0:filename.index(os.path.sep)]

    list = []
    for dirpath, dirnames, files in os.walk(dir):
        if re.findall(r'[/\\+]androidTest[/\\+]', dirpath) or '/.' in dirpath:
            continue
        if dir0 in dirnames and os.path.isfile(os.path.join(dirpath, filename)):
            list.append(dirpath)

    if len(list) == 1:
        return list[0]
    elif len(list) > 1:
        maxt = 0
        maxd = None
        for ddir in list:
            lastModified = 0
            for dirpath, dirnames, files in os.walk(dir):
                for fn in files:
                    if fn.endswith('.class'):
                        lastModified = os.path.getmtime(os.path.join(dirpath, fn))
            if lastModified > maxt:
                maxt = lastModified
                maxd = ddir
        return maxd
    else:
        return os.path.join(dir, 'debug')


def get_maven_libs(projs):
    maven_deps = []
    for proj in projs:
        str = open_as_text(os.path.join(proj, 'build.gradle'))
        str = remove_comments(str)

        # 获取maven的 lib 依赖
        for m in re.finditer(r'dependencies\s*\{', str):
            depends = balanced_braces(str[m.start():])

            # compile的格式:
            # compile 'com.facebook.fresco:fresco:0.6.0+'
            for mvndep in re.findall(r'''compile\s+['"](.+:.+:.+)(?:@*)?['"]''', depends):
                mvndeps = mvndep.split(':')
                if not mvndeps in maven_deps:
                    maven_deps.append(mvndeps)
    return maven_deps


# 获取 libs 对应的 maven jars
def get_maven_jars(libs):
    if not libs:
        return []
    jars = []
    maven_path_prefix = []

    # 1. ~/.gralde/caches
    gradle_home = os.path.join(os.path.expanduser('~'), '.gradle', 'caches')

    for dirpath, dirnames, files in os.walk(gradle_home):
        # search in ~/.gradle/**/GROUP_ID/ARTIFACT_ID/VERSION/**/*.jar
        # libs的格式?
        # ["com.facebook.fresco", "fresco", "0.6.0+"]
        # dirpath为当前遍历的路径
        # dirname为 dirpath下类型为DIR的东西
        for mvndeps in libs:
            if mvndeps[0] in dirnames:
                dir1 = os.path.join(dirpath, mvndeps[0], mvndeps[1])

                if os.path.isdir(dir1):
                    dir2 = os.path.join(dir1, mvndeps[2])
                    if os.path.isdir(dir2):
                        maven_path_prefix.append(dir2)
                    else:
                        prefix = mvndeps[2]
                        if '+' in prefix:
                            prefix = prefix[0:prefix.index('+')]
                        maxdir = ''
                        for subd in os.listdir(dir1):
                            if subd.startswith(prefix) and subd > maxdir:
                                maxdir = subd
                        if maxdir:
                            maven_path_prefix.append(os.path.join(dir1, maxdir))
        for dirprefix in maven_path_prefix:
            if dirpath.startswith(dirprefix):
                for fn in files:
                    if fn.endswith('.jar') and not fn.startswith('.') and not fn.endswith(
                            '-sources.jar') and not fn.endswith('-javadoc.jar'):
                        jars.append(os.path.join(dirpath, fn))
                break
    return jars


def scan_port(adbpath, pnlist, projlist):
    """
    返回可用的 <端口, project_dir, packagename>
    :param adbpath:
    :param pnlist:
    :param projlist:
    :return:
    """
    port = 0
    prodir = None
    packagename = None
    for i in range(0, 10):
        try_port = (41128 + i)
        # 1. 通过adb做端口映射
        cexec([adbpath, 'forward', 'tcp:%d' % try_port, 'tcp:%d' % try_port])

        # 2. 然后 pnlist
        #        projlist
        output = curl('http://127.0.0.1:%d/packagename' % try_port, ignoreError=True)
        if output and output in pnlist:
            # 如果返回的 packagename可以接受
            index = pnlist.index(output)  # index of this app in projlist

            # 获取 app的状态
            # appstate是如何定义的呢?
            state = curl('http://127.0.0.1:%d/appstate' % try_port, ignoreError=True)
            if state and int(state) >= 2:
                # starte >= 2 表示界面可见
                port = try_port
                prodir = projlist[index]
                packagename = output
                break

    # 删除多余的端口映射
    for i in range(0, 10):
        if (41128 + i) != port:
            cexec([adbpath, 'forward', '--remove', 'tcp:%d' % (41128 + i)], callback=None)
    return port, prodir, packagename


if __name__ == "__main__":

    dir = '.'
    sdkdir = None
    jdkdir = None

    starttime = time.time()

    # 1. 手动指定: Android SDK Path/JDK Path以及Project
    if len(sys.argv) > 1:
        parser = argparse.ArgumentParser()
        parser.add_argument('--sdk', help='specify Android SDK path')
        parser.add_argument('--jdk', help='specify JDK path')
        parser.add_argument('project')
        args = parser.parse_args()
        if args.sdk:
            sdkdir = args.sdk
        if args.jdk:
            jdkdir = args.jdk
        if args.project:
            dir = args.project

    # 2. 获取有的 project list
    projlist = [i for i in list_projects(dir) if is_launchable_project(i)]

    # 3. 获取默认的android sdk/java sdk
    if not sdkdir:
        sdkdir = get_android_sdk(dir)
        if not sdkdir:
            print('android sdk not found, specify in local.properties or export ANDROID_HOME')
            exit(2)

    if not projlist:
        print('no valid android project found in ' + os.path.abspath(dir))
        exit(3)

    # 4. 如何获取packagename呢?
    pnlist = [package_name_fromapk(i, sdkdir) for i in projlist]
    portlist = [0 for i in pnlist]

    # 获取adb
    adbpath = get_adb(sdkdir)

    if not adbpath:
        print('adb not found in %s/platform-tools' % sdkdir)
        exit(4)

    # 1. 进行端口扫描
    #    如果同时运行多个apk, 如何知道哪一个apk是当前正在调试的呢?) appstate
    port, dir, packagename = scan_port(adbpath, pnlist, projlist)

    # 2. 没有启动(则继续尝试等待)
    if port == 0:
        # 启动app, 并且进行端口扫描
        # launch app
        latest_package = get_latest_packagename(projlist, sdkdir)
        if latest_package:
            cexec([adbpath, 'shell', 'monkey', '-p', latest_package, '-c', 'android.intent.category.LAUNCHER', '1'], callback=None)
            for i in range(0, 6):
                # try 6 times to wait the application launches
                port, dir, packagename = scan_port(adbpath, pnlist, projlist)
                if port:
                    break
                time.sleep(0.25)

    if port == 0:
        print('package %s not found, make sure your project is properly setup and running' % (
            len(pnlist) == 1 and pnlist[0] or pnlist))
        exit(5)


    URL_LCAST = 'http://127.0.0.1:%d/lcast' % port
    URL_PUSH_DEX = 'http://127.0.0.1:%d/pushdex' % port
    URL_LAUNCH = 'http://127.0.0.1:%d/launcher' % port
    URL_PCAST = 'http://127.0.0.1:%d/pcast' % port

    URL_IDS = 'http://127.0.0.1:%d/ids.xml' % port
    URL_PUBLIC = 'http://127.0.0.1:%d/public.xml' % port

    # 将资源推送给手机
    URL_PUSH_RES = 'http://127.0.0.1:%d/pushres' % port

    # 用于判断手机是否支持: ART
    URL_VM_VERSION = 'http://127.0.0.1:%d/vmversion' % port

    is_gradle = is_gradle_project(dir)

    android_jar = get_android_jar(sdkdir)
    if not android_jar:
        print('android.jar not found !!!\nUse local.properties or set ANDROID_HOME env')
        exit(7)
    deps = deps_list(dir)

    # build/lcast
    bindir = is_gradle and os.path.join(dir, 'build', 'lcast') or os.path.join(dir, 'bin', 'lcast')

    # check if the /res and /src has changed
    lastBuild = 0

    # 获取apk的路径(fpath, 以及build的时间)
    rdir = is_gradle and os.path.join(dir, 'build', 'outputs', 'apk') or os.path.join(dir, 'bin')
    if os.path.isdir(rdir):
        for fn in os.listdir(rdir):
            if fn.endswith('.apk') and not '-androidTest' in fn:
                fpath = os.path.join(rdir, fn)
                lastBuild = max(lastBuild, os.path.getmtime(fpath))


    # dir, deps如何处理呢?
    adeps = []
    adeps.extend(deps)
    adeps.append(dir)

    latestResModified = 0
    latestSrcModified = 0
    srcs = []
    msrclist = []
    assetdirs = []

    for dep in adeps:
        adir = assetdir(dep)

        # A. 获取: asset的变化情况
        if adir:
            latestModified = os.path.getmtime(adir)
            for dirpath, dirnames, files in os.walk(adir):
                for dirname in dirnames:
                    if not dirname.startswith('.'):
                        latestModified = max(latestModified, os.path.getmtime(os.path.join(dirpath, dirname)))
                for fn in files:
                    if not fn.startswith('.'):
                        fpath = os.path.join(dirpath, fn)
                        latestModified = max(latestModified, os.path.getmtime(fpath))
            latestResModified = max(latestResModified, latestModified)
            if latestModified > lastBuild:
                assetdirs.append(adir)  # 整个asset dir都放在里面

        # B. 获取 resource 的变化情况
        rdir = resdir(dep)
        if rdir:
            for subd in os.listdir(rdir):
                if os.path.isdir(os.path.join(rdir, subd)) and isResName(subd):
                    for fn in os.listdir(os.path.join(rdir, subd)):
                        fpath = os.path.join(rdir, subd, fn)
                        if os.path.isfile(fpath) and not fn.startswith('.'):
                            latestResModified = max(latestResModified, os.path.getmtime(fpath))

        # 返回源码的修改时间，以及文件个数
        (sdir, scount, smt) = srcdir2(dep, lastBuild=lastBuild, list=msrclist)
        if sdir:
            srcs.append(sdir)
            latestSrcModified = max(latestSrcModified, smt)
    resModified = latestResModified > lastBuild
    srcModified = latestSrcModified > lastBuild


    targets = ''
    if resModified and srcModified:
        targets = 'both /res and /src'
    elif resModified:
        targets = '/res'
    elif srcModified:
        targets = '/src'
    else:
        print('%s has no /res or /src changes' % (packagename))
        exit(0)

    if is_gradle:
        print('cast %s:%d as gradle project with %s changed (v%s)' % (packagename, port, targets, __version__))
    else:
        print('cast %s:%d as eclipse project with %s changed (v%s)' % (packagename, port, targets, __version__))

    # prepare to reset
    # 如果代码修改了，直接进行: pcast
    if srcModified:
        curl(URL_PCAST, ignoreError=True)

    if resModified:

        # build/lcast
        # build/lcast/res
        # build/lcast/res/values
        #                 values/ids.xml
        #                 values/public.xml
        #
        binresdir = os.path.join(bindir, 'res')
        if not os.path.exists(os.path.join(binresdir, 'values')):
            os.makedirs(os.path.join(binresdir, 'values'))



        data = curl(URL_IDS, exitcode=8)
        with open(os.path.join(binresdir, 'values/ids.xml'), 'w') as fp:
            fp.write(data)
        data = curl(URL_PUBLIC, exitcode=9)
        with open(os.path.join(binresdir, 'values/public.xml'), 'w') as fp:
            fp.write(data)

        # Get the assets path
        apk_path = get_apk_path(dir)
        if apk_path:
            # build/lcast/assets
            assets_path = os.path.join(bindir, "assets")
            if os.path.isdir(assets_path):
                shutil.rmtree(assets_path)
            get_asset_from_apk(apk_path, bindir)

        aaptpath = get_aapt(sdkdir)
        if not aaptpath:
            print('aapt not found in %s/build-tools' % sdkdir)
            exit(10)


        # 生成 res.zip
        aaptargs = [aaptpath, 'package', '-f', '--auto-add-overlay', '-F', os.path.join(bindir, 'res.zip')]
        aaptargs.append('-S')
        aaptargs.append(binresdir)
        rdir = resdir(dir)
        if rdir:
            aaptargs.append('-S')
            aaptargs.append(rdir)
        for dep in reversed(deps):
            rdir = resdir(dep)
            if rdir:
                aaptargs.append('-S')
                aaptargs.append(rdir)
        if is_gradle:
            for dep in reversed(list_aar_projects(dir, deps)):
                aaptargs.append('-S')
                aaptargs.append(dep)
        for assetdir in assetdirs:
            aaptargs.append('-A')
            aaptargs.append(assetdir)
        if os.path.isdir(assets_path):
            aaptargs.append('-A')
            aaptargs.append(assets_path)
        aaptargs.append('-M')
        aaptargs.append(manifestpath(dir))
        aaptargs.append('-I')
        aaptargs.append(android_jar)

        print("生成 res.zip文件：")
        print(" ".join(aaptargs))
        cexec(aaptargs, exitcode=18)

        # 将 res.zip 推送到android手机
        with open(os.path.join(bindir, 'res.zip'), 'rb') as fp:
            curl(URL_PUSH_RES, body=fp.read(), exitcode=11)

    if srcModified:
        vmversion = curl(URL_VM_VERSION, ignoreError=True)
        if vmversion == None:
            vmversion = ''
        if vmversion.startswith('1'):
            print('cast dex to dalvik vm is not supported, you need ART in Android 5.0')
        elif vmversion.startswith('2'):
            javac = get_javac(jdkdir)
            if not javac:
                print('javac is required to compile java code, config your PATH to include javac')
                exit(12)

            launcher = curl(URL_LAUNCH, exitcode=13)

            # 获取所有的 jar 文件
            classpath = [android_jar]
            for dep in adeps:
                dlib = libdir(dep)
                if dlib:
                    for fjar in os.listdir(dlib):
                        if fjar.endswith('.jar'):
                            classpath.append(os.path.join(dlib, fjar))
            if is_gradle:
                # jars from maven cache
                maven_libs = get_maven_libs(adeps)
                maven_libs_cache_file = os.path.join(bindir, 'cache-javac-maven.json')
                maven_libs_cache = {}
                if os.path.isfile(maven_libs_cache_file):
                    try:
                        with open(maven_libs_cache_file, 'r') as fp:
                            maven_libs_cache = json.load(fp)
                    except:
                        pass
                if maven_libs_cache.get('version') != 1 or not maven_libs_cache.get(
                        'from') or sorted(maven_libs_cache['from']) != sorted(maven_libs):
                    if os.path.isfile(maven_libs_cache_file):
                        os.remove(maven_libs_cache_file)
                    maven_libs_cache = {}
                maven_jars = []
                if maven_libs_cache:
                    maven_jars = maven_libs_cache.get('jars')
                elif maven_libs:
                    maven_jars = get_maven_jars(maven_libs)
                    cache = {'version': 1, 'from': maven_libs, 'jars': maven_jars}
                    try:
                        with open(maven_libs_cache_file, 'w') as fp:
                            json.dump(cache, fp)
                    except:
                        pass
                if maven_jars:
                    classpath.extend(maven_jars)
                # aars from exploded-aar
                darr = os.path.join(dir, 'build', 'intermediates', 'exploded-aar')
                # TODO: use the max version
                for dirpath, dirnames, files in os.walk(darr):
                    if re.findall(r'[/\\+]androidTest[/\\+]', dirpath) or '/.' in dirpath:
                        continue
                    for fn in files:
                        if fn.endswith('.jar'):
                            classpath.append(os.path.join(dirpath, fn))
                # R.class
                classesdir = search_path(os.path.join(dir, 'build', 'intermediates', 'classes'),
                                         launcher and launcher.replace('.',
                                                                       os.path.sep) + '.class' or '$')
                classpath.append(classesdir)
            else:
                # R.class
                classpath.append(os.path.join(dir, 'bin', 'classes'))

            binclassesdir = os.path.join(bindir, 'classes')
            shutil.rmtree(binclassesdir, ignore_errors=True)
            os.makedirs(binclassesdir)

            javacargs = [javac, '-target', '1.7', '-source', '1.7', '-encoding', 'UTF-8']
            javacargs.append('-cp')
            javacargs.append(os.pathsep.join(classpath))
            javacargs.append('-d')
            javacargs.append(binclassesdir)
            javacargs.append('-sourcepath')
            javacargs.append(os.pathsep.join(srcs))
            javacargs.extend(msrclist)


            # remove all cache if javac fail
            def remove_cache_and_exit(args, code, stdout, stderr):
                if code:
                    maven_libs_cache_file = os.path.join(bindir, 'cache-javac-maven.json')
                    if os.path.isfile(maven_libs_cache_file):
                        os.remove(maven_libs_cache_file)
                cexec_fail_exit(args, code, stdout, stderr)

            print("javacargs: ")
            print(" ".join(javacargs))

            cexec(javacargs, callback=remove_cache_and_exit, exitcode=19)

            dxpath = get_dx(sdkdir)
            if not dxpath:
                print('dx not found in %s/build-tools' % sdkdir)
                exit(14)
            dxoutput = os.path.join(bindir, 'classes.dex')
            if os.path.isfile(dxoutput):
                os.remove(dxoutput)
            addPath = None
            if os.name == 'nt':
                # fix system32 java.exe issue
                addPath = os.path.abspath(os.path.join(javac, os.pardir))

            print("Dex Create: ")
            print(" ".join([dxpath, '--dex', '--output=%s' % dxoutput, binclassesdir]))

            cexec([dxpath, '--dex', '--output=%s' % dxoutput, binclassesdir], addPath=addPath,
                  exitcode=20)

            # 推送代码
            with open(dxoutput, 'rb') as fp:
                curl(URL_PUSH_DEX, body=fp.read(), exitcode=15)

        else:
            if is_gradle:
                print('LayoutCast library out of date, please sync your project with gradle')
            else:
                print('libs/lcast.jar is out of date, please update')

    # lcast
    curl(URL_LCAST, ignoreError=True)

    # 工作结束
    cexec([adbpath, 'forward', '--remove', 'tcp:%d' % port], callback=None)

    elapsetime = time.time() - starttime
    print('finished in %dms' % (elapsetime * 1000))
