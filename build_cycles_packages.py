import platform
on_macos = platform.system()=='Darwin'

from typing import Callable

import copy

from dataclasses import dataclass
from typing import List
from pathlib import Path

import argparse

import sys

import urllib.request
import tarfile
import zipfile
from typing import Union
import subprocess

@dataclass
class Package:
    __slots__ = ["name", "version", "url", "local", "acquire", "get_include_dir",
                 "get_library_dir", "patcher", "builder", "prepare_package",
                 "dependencies", "extract_location"]
    name : str
    version : str
    url : str
    local : Path
    acquire : Callable[..., None]
    get_include_dir : Callable[..., str]
    get_library_dir : Callable[..., str]
    patcher : Callable[..., None]
    builder : Callable[..., None]
    prepare_package: Callable[..., None]
    dependencies : List[str]
    extract_location : str

    def acquire_it(self):
        if self.acquire:
            return self.acquire(self)

    def build_it(self):
        if self.builder:
            return self.builder(self)

    def patch_it(self):
        if self.patcher:
            return self.patcher(self)

# will gather all the different packages that exist.
packages : List[Package] = list()

def register_package(func : Callable[[None], Package]):
    """Register package function"""
    package = func()
    packages.append(package)

    return func

def no_patches(self : Package):
    print(f"No patches for {self.name}")

msbuild = Path(r'C:\Program Files (x86)\Microsoft Visual Studio\2019\Professional\MSBuild\Current\Bin\MSBuild.exe')

current_path = Path('.').resolve()
dl_folder = current_path / '..' / 'cycles_dependencies_dl'
dl_folder = dl_folder.resolve()
build_folder = current_path / '..' / 'cycles_dependencies_build'
build_folder = build_folder.resolve()

parser = argparse.ArgumentParser()
parser.add_argument('--clean-dl', action=argparse.BooleanOptionalAction, default=True)
parser.add_argument('--clean-build', action=argparse.BooleanOptionalAction, default=True)

args = parser.parse_args()

def download_progress_reporter(block_count : int, block_size_in_bytes : int, total_size : int) -> None:
    if total_size > -1:
        perc = block_count * block_size_in_bytes / total_size * 100
        print(f"{block_count * block_size_in_bytes} bytes ({perc:.1f}%) downloaded of {total_size}\r", end="")
    else:
        perc = "~"
        print(f"{block_count * block_size_in_bytes} bytes downloaded (total size unknown)\r", end="")

def folder_recursive_delete(folder : Path) -> None:
    if not folder.exists() or not folder.is_dir():
        return
    for child in folder.iterdir():
        if child.is_dir():
            folder_recursive_delete(child)
        else:
            child.unlink()
    folder.rmdir()

def download_and_extract_package(package : Package) -> None:
    dep_local = package.local
    dep_url = package.url
    if not dep_local.exists():
        #print(f"Start downloading {package.name} {package.version}...")
        dep_local_zip, httpmessage = urllib.request.urlretrieve(dep_url, str(dep_local), download_progress_reporter)
        #print(f"...download to {dep_local} complete.")
        print(f"Extracting {package.name}...")
        dep_local_zip = Path(dep_local_zip)
        if dep_local != dep_local_zip:
            print(f"Archive download location different from specified")
    else:
        print(f"{package.name} ({dep_url}) already downloaded as {dep_local}.")

    if dep_local and dep_local.exists():
        def extract_only_when_necessary(archive : Union[zipfile.ZipFile, tarfile.TarFile], local_path : Path, target_path : Path, extracted_location : Path) -> None:
            if not extracted_location.exists():
                print(f"extracting {local_path}...")
                archive.extractall(target_path)
                print(f"... extracting {local_path} complete.")
            else:
                print(f"Archive {local_path} already extracted.")

        def extract_archive(archive : Union[zipfile.ZipFile, tarfile.TarFile]):
            if type(archive) == zipfile.ZipFile:
                root = zipfile.Path(archive)
                children = [p for p in root.iterdir()]
                if len(children)==1 and children[0].is_dir():
                    package.extract_location = build_folder / children[0].name
                    target_folder = build_folder
                else:
                    stem = dep_local.stem
                    target_folder = build_folder / stem
                    package.extract_location = target_folder
            else:
                if archive.getmembers()[0].isdir():
                    target_folder = build_folder
                    package.extract_location = target_folder / archive.getmembers()[0].name
                else:
                    stem = dep_local.stem
                    target_folder = build_folder / stem
                    package.extract_location = target_folder

            extract_only_when_necessary(archive, dep_local, target_folder, package.extract_location)

        if dep_local.suffix == '.zip':
            with zipfile.ZipFile(dep_local, mode='r') as dep_zip:
                extract_archive(dep_zip)
        else:
            with tarfile.open(name=dep_local, mode='r:gz') as dep_zip:
                extract_archive(dep_zip)


if args.clean_dl:
    if dl_folder.exists():
        print(f"Cleaning out {dl_folder}...")
        folder_recursive_delete(dl_folder)
        print("... clean complete.")
    dl_folder.mkdir()
else:
    if not dl_folder.exists():
        dl_folder.mkdir()
    print("Not cleaning out old download results")

if args.clean_build:
    if build_folder.exists():
        print(f"Cleaning out {build_folder}...")
        folder_recursive_delete(build_folder)
        print("... clean complete.")
    build_folder.mkdir()
else:
    if not build_folder.exists():
        build_folder.mkdir()
    print("Not cleaning out build results")

@register_package
def boost():
    boost_version = '1.77.0'
    boost_version_ = boost_version.replace('.', '_')
    boost_url = f'https://boostorg.jfrog.io/artifactory/main/release/{boost_version}/source/boost_{boost_version_}.zip'
    def boost_include_dir(self) -> str:
        boost_inc = self.extract_location / '..' / 'boost_install' / 'include'
        boost_inc = boost_inc.resolve()
        return f"{boost_inc}"

    def boost_library_dir(self) -> str:
        boost_lib = (self.extract_location / '..' / 'boost_install' / 'lib').resolve()
        return f"{boost_lib}"

    def boost_package(self) -> None:
        pass

    def boost_build(self) -> None:
        already_built = build_folder / 'boost.built'
    
        boost_install = self.extract_location / '..' / 'boost_install'
        if not already_built.exists():
            if boost_install.exists():
                folder_recursive_delete(boost_install)
            boost_install.mkdir()
    
            if not on_macos:
                bootstrap = [f"{self.extract_location / 'bootstrap.bat' }"]
                b2exe = f"{self.extract_location / 'b2.exe' }"
                toolsets = ['14.1', '14.2']
            else:
                bootstrap = [f"{self.extract_location / 'bootstrap.sh' }"]
                buildsh = f"{self.extract_location / 'tools/build/src/engine/build.sh' }"
                b2exe = f"{self.extract_location / 'b2' }"
                chmod_process = subprocess.run(['chmod', 'u+x', bootstrap[0], buildsh])
                if chmod_process.returncode!=0:
                    print("Could not change bootstrap.sh permissions.")
                    raise Exception("Problem setting bootstrap.sh permissions.")
                toolsets = ['clang']
    
            print("Bootstrapping Boost... ")
            bootstrap_process = subprocess.run(bootstrap, cwd=self.extract_location, capture_output=True)
            if bootstrap_process.returncode!=0:
                print("Problem bootstrapping Boost:")
                print(f"{bootstrap_process.stdout}")
                print(f"{bootstrap_process.stderr}")
                raise Exception("Problem bootstrapping Boost.")
            print("Bootstrapping Boost complete.")
    
    
            variants = ['release', 'debug']
            for toolset in toolsets:
                for variant in variants:
                    boost_build = self.extract_location / '..' / f'boost_build{variant}'
                    boost_stage = self.extract_location / '..' / f'boost_stage{variant}'
                    if boost_build.exists():
                        folder_recursive_delete(boost_build)
                    boost_build.mkdir()
                    if boost_stage.exists():
                        folder_recursive_delete(boost_stage)
                    boost_stage.mkdir()
    
                    boostbuild= [
                        b2exe,
                        "-d+2",
                        "-q",
                        f"--prefix={boost_install}",
                        "--no-cmake-config",
                        f"--stagedir={boost_stage}",
                        "--build-type=minimal",
                        f"--build-dir={boost_build}",
                        "--layout=tagged",
                        f"--buildid=RH-{toolset.replace('.', '')}" if on_macos else f"--buildid=RH-v{toolset.replace('.', '')}",
                        f"variant={variant}",
                        "warnings=off",
                        f"toolset={toolset}" if on_macos else f"toolset=msvc-{toolset}",
                        "link=shared",
                        "threading=multi",
                        "runtime-link=shared",
                        "address-model=64",
                        "--with-date_time",
                        "--with-chrono",
                        "--with-filesystem",
                        "--with-locale",
                        "--with-regex",
                        "--with-system",
                        "--with-thread",
                        "--with-serialization",
                        "stage",
                        "install"
                    ]
    
                    print(f"Building Boost: {toolset}, {variant}... ")
                    boostbuild_process = subprocess.run(boostbuild, cwd=self.extract_location, capture_output=True)
                    if boostbuild_process.returncode!=0:
                        print(f"Problem building Boost, {toolset}, {variant}:")
                        print(f"{boostbuild_process.stdout}")
                        print(f"{boostbuild_process.stderr}")
                        raise Exception(f"Problem building Boost. {toolset}, {variant}")
                    print(f"Building Boost complete. {toolset}, {variant}")
            already_built.touch()

    boost_local = dl_folder / f'boost_{boost_version_}.zip'

    boost_dep = Package("Boost", boost_version, boost_url, boost_local,
                            download_and_extract_package,
                            boost_include_dir, boost_library_dir, no_patches,
                            boost_build, boost_package,
                            [], '')
    return boost_dep

def openexr_include_dir(self) -> str:
    install_dir = (self.extract_location / '..' / 'openexr_install' / 'include').resolve()
    return f"{install_dir}"

def openexr_library_dir(self) -> str:
    return ""

def openexr_package(self) -> None:
    pass

def openexr_build(self) -> None:
    already_built = build_folder / 'openexr.built'
    # we shouldn't build in the source directory (extract_location)
    build_dir = Path(self.extract_location) / '..' / 'openexr_build'
    install_dir = Path(self.extract_location) / '..' / 'openexr_install'

    if not already_built.exists():
        if build_dir.exists():
            folder_recursive_delete(build_dir)
        build_dir.mkdir()

        if install_dir.exists():
            folder_recursive_delete(install_dir)
        install_dir.mkdir()

        for p in packages:
            if p.name.lower() == 'zlib':
                zlib_library = Path(p.get_library_dir(p))
                zlib_include_dir = Path(p.get_include_dir(p))

        openexr_config_cmake = [
            'cmake',
            f'-DCMAKE_SYSTEM_PREFIX={install_dir}',
            f'-DCMAKE_INSTALL_PREFIX={install_dir}',
            '-DOPENEXR_LIB_SUFFIX=-RH-2_5',
            '-DILMBASE_LIB_SUFFIX=-RH-2_5',
            f'-DZLIB_LIBRARY={zlib_library}',
            f'-DZLIB_INCLUDE_DIR={zlib_include_dir}',
            '-DPYILMBASE_ENABLE=OFF',
            f"{self.extract_location}"
        ]

        print("Configuring OpenEXR")
        openexr_config_process = subprocess.run(openexr_config_cmake, cwd=build_dir, encoding='utf-8', capture_output=True)
        if openexr_config_process.returncode!=0:
            print(openexr_config_process.stdout)
            print(openexr_config_process.stderr)
            raise Exception("OpenEXR configuration failed")

        print("OpenEXR configured.")

        openexr_build_cmake = [
            'cmake',
            '--build',
            '.',
            '--target',
            'install',
            '--config',
            'Release'
        ]
        print("Building OpenEXR")
        openexr_build_process = subprocess.run(openexr_build_cmake, cwd=build_dir, encoding='utf-8', capture_output=True)
        if openexr_build_process.returncode!=0:
            print(openexr_build_process.stdout)
            print(openexr_build_process.stderr)
            raise Exception("OpenEXR build failed")

        print("OpenEXR built.")

        already_built.touch()
@register_package
def openexr():
    openexr_version = '2.5.5'
    openexr_url = f'https://github.com/AcademySoftwareFoundation/openexr/archive/refs/tags/v{openexr_version}.zip'
    openexr_local = dl_folder / f'openexr_{openexr_version}.zip'
    openexr_dep = Package("OpenEXR", openexr_version, openexr_url, openexr_local,
                            download_and_extract_package,
                            openexr_include_dir, openexr_library_dir, no_patches,
                            openexr_build, openexr_package,
                            ['zlib'], '')
    return openexr_dep

def oiio_include_dir(self) -> str:
    return f"{self.extract_location}"

def oiio_library_dir(self) -> str:
    return f"{self.extract_location}"

def oiio_package(self) -> None:
    pass

def oiio_build(self) -> None:
    already_built = build_folder / 'oiio.built'
    build_dir = self.extract_location / '..' / 'oiio_build'
    install_dir = self.extract_location / '..' / 'oiio_install'

    if not already_built.exists():
        if build_dir.exists():
            folder_recursive_delete(build_dir)
        build_dir.mkdir()

        if install_dir.exists():
            folder_recursive_delete(install_dir)
        install_dir.mkdir()

        for p in packages:
            if p.name.lower() == 'zlib':
                zlib_library = p.get_library_dir(p)
                zlib_root = p.get_include_dir(p)
            if p.name.lower() == 'libtiff':
                libtiff_include = p.get_include_dir(p)
                libtiff_root = (Path(libtiff_include) / '..') .resolve()
            if p.name.lower() == 'openexr':
                openexr_root = (Path(p.get_include_dir(p)) / '..' ) .resolve()
            if p.name.lower() == 'libjpeg':
                libjpeg_include = p.get_include_dir(p)
                libjpeg_root = (Path(libjpeg_include) / '..' ) .resolve()
            if p.name.lower() == 'boost':
                boost_library_dir = p.get_library_dir(p)
                boost_include_dir = p.get_include_dir(p)
                boost_root = Path(boost_include_dir) / '..'
                boost_root = boost_root.resolve()
                if on_macos:
                    prefix = 'lib'
                    postfix = 'clang.dylib'
                else:
                    prefix = ''
                    postfix = 'v141.lib'
            
                _boost_libraries = [
                    'boost_atomic-mt-x64-RH-',
                    'boost_chrono-mt-x64-RH-',
                    'boost_date_time-mt-x64-RH-',
                    'boost_filesystem-mt-x64-RH-',
                    'boost_locale-mt-x64-RH-',
                    'boost_regex-mt-x64-RH-',
                    'boost_serialization-mt-x64-RH-',
                    'boost_system-mt-x64-RH-',
                    'boost_thread-mt-x64-RH-',
                    'boost_wserialization-mt-x64-RH-'
                ]
                boost_libraries = ';'.join([f'{prefix}{lib}{postfix}' for lib in _boost_libraries])
        oiio_config_cmake = [
            'cmake',
            '-DCMAKE_VERBOSE_MAKEFILE=ON',
            f'-DCMAKE_SYSTEM_PREFIX={install_dir}',
            f'-DCMAKE_INSTALL_PREFIX={install_dir}',
            '-DUSE_PTHREAD=OFF',
            '-DUSE_PYTHON=OFF',
            '-DUSE_CCACHE=OFF',
            '-DOIIO_BUILD_TOOLS=OFF',
            '-DOIIO_BUILD_TESTS=OFF',
            '-DBUILD_TESTING=OFF',
            '-DBUILD_DOCS=OFF',
            '-DBUILD_FMT_FORCE=OFF',
            '-DBUILD_MISSING_DEPS=OFF',
            '-DINSTALL_DOCS=OFF',
            '-DINSTALL_FONTS=OFF',
            '-DOIIO_THREAD_ALLOW_DCLP=OFF',
            '-DENABLE_GIF=OFF',
            '-DENABLE_BZIP2=OFF',
            '-DENABLE_FREETYPE=OFF',
            '-DENABLE_HDF5=OFF',
            '-DENABLE_LIBHEIF=OFF',
            '-DENABLE_LibRaw=OFF',
            '-DENABLE_OPENGL=OFF',
            '-DENABLE_OPENGL_gl=OFF',
            '-DENABLE_OPENGL_glu=OFF',
            '-DENABLE_OPENJPEG=OFF',
            '-DENABLE_OpenCV=OFF',
            '-DENABLE_Ptex=OFF',
            '-DENABLE_Qt5=OFF',
            '-DENABLE_LBSQUISH=OFF',
            '-DENABLE_NUKE_DOIMAGE=OFF',
            '-DENABLE_WEBP=OFF',
            '-DOIIO_LIBNAME_SUFFIX=RH',
            '-DLINKSTATIC=ON',
            f'-DZLIB_ROOT={zlib_root}',
            f'-DZLIB_LIBRARY_DEBUG={zlib_library}',
            f'-DZLIB_LIBRARY_RELEASE={zlib_library}',
            f'-DBoost_ROOT={boost_root}',
            '-DBOOST_CUSTOM=ON',
            '-DBoost_VERSION=1.77',
            f'-DBoost_INCLUDE_DIRS={boost_include_dir}',
            f'-DBoost_LIBRARY_DIRS={boost_library_dir}',
            f'-DBoost_LIBRARIES={boost_libraries}',
            f'-DOpenEXR_ROOT={openexr_root}',
            f'-DTIFF_ROOT={libtiff_root}',
            f'-DJPEG_INCLUDE_DIR={libjpeg_include}',
            f'-DJPEG_ROOT={libjpeg_root}',
            f"{self.extract_location}"
        ]
        
        print(oiio_config_cmake)
        
        oiio_config_process = subprocess.run(oiio_config_cmake, cwd=build_dir, encoding='utf-8', capture_output=True)
        if oiio_config_process.returncode!=0:
            print(oiio_config_process.stdout)
            print(oiio_config_process.stderr)
            raise Exception("OpenImageIO configuration failed")
        else:
            print("OpenImageIO configured.")

        oiio_build_cmake = [
            'cmake',
            '--build',
            '.',
            '--target',
            'install',
            '--config',
            'Release'
        ]
        oiio_build_process = subprocess.run(oiio_build_cmake, cwd=build_dir, encoding='utf-8', capture_output=True)
        if oiio_build_process.returncode!=0:
            print(oiio_build_process.stdout)
            print(oiio_build_process.stderr)
            raise Exception("OpenImageIO build failed")
        else:
            print("OpenImageIO built")

        already_built.touch()

@register_package
def oiio():
    oiio_version = '2.2.19.0'
    oiio_url = f'https://github.com/OpenImageIO/oiio/archive/refs/tags/v{oiio_version}.zip'
    oiio_local = dl_folder / f'OpenImageIOv{oiio_version}.zip'
    oiio_dep = Package("OpenImageIO", oiio_version, oiio_url, oiio_local,
                            download_and_extract_package,
                            oiio_include_dir, oiio_library_dir, no_patches,
                            oiio_build, oiio_package,
                            ["openexr", "boost", "libpng", "libtiff", "libjpeg"], '')
    return oiio_dep

def zlib_include_dir(self) -> str:
    return f"{self.extract_location}"

def zlib_library_dir(self) -> str:
    if on_macos:
        return f"{Path(self.extract_location) / 'libz.a'}"
    else:
        return f"{Path(self.extract_location) / 'contrib' / 'vstudio' / 'vc14' / 'x64' / 'ZlibStatRelease' / 'zlibstat.lib'}"

def zlib_package(self) -> None:
    pass

def zlib_patch(self):
    if on_macos:
        return

    patch_file = current_path / 'patches' / 'zlib_build_system.patch'
    patch_file_applied = build_folder / 'zlib_build_system.patch.applied'

    if not patch_file_applied.exists():
        patch_command = [
            'git',
            'apply',
            '--ignore-space-change',
            '--ignore-whitespace',
            '--whitespace=nowarn',
            '-p1',
            f"{patch_file}"
        ]
        patch_process = subprocess.run(patch_command, cwd=self.extract_location, encoding='utf-8', universal_newlines='\n', capture_output=True)
        if patch_process.returncode!=0:
            print(patch_process.stderr)
            print(patch_process.stdout)
            raise Exception("Zlib patching failed.")
        print(patch_process.stdout)
        patch_file_applied.touch()
        print("Zlib patch successfully applied.")
    else:
        print("Zlib patch already applied.")

def zlib_build_windows(self) -> None:
    already_built = build_folder / 'zlib.built'

    if not already_built.exists():
        asmcode = self.extract_location / 'contrib' / 'masmx64' / 'bld_ml64.bat'
        asmcode_wd = asmcode.parent
        sln = self.extract_location / 'contrib' / 'vstudio' / 'vc14' / 'zlibvc.sln'

        build_settings = [f"{msbuild}",
                        f"{sln}",
                        "/t:zlibstat",
                        "/p:Configuration=Release",
                        "/p:Platform=x64",
                        "/m"
        ]

        print(build_settings)

        asm_process = subprocess.run([f"{asmcode}"], cwd=f"{asmcode_wd}", encoding='utf-8', universal_newlines='\n', capture_output=True)
        print(asm_process.stdout)

        completed_process = subprocess.run(build_settings, encoding='utf-8', universal_newlines='\n', capture_output=True)
        print(completed_process.stdout)


        print(f"Use {sln}, {sln.exists()}")
        already_built.touch()


def zlib_build_macos(self) -> None:
    already_built = build_folder / 'zlib.built'

    if not already_built.exists():
        configure = self.extract_location / 'configure'

        build_settings = [f"{configure}",
                        "--static",
                        "--64"
        ]

        print(build_settings)

        chmod_process = subprocess.run(['chmod', 'u+x', configure], cwd=f"{self.extract_location}", encoding='utf-8', universal_newlines='\n', capture_output=True)

        configure_process = subprocess.run(build_settings, cwd=f"{self.extract_location}", encoding='utf-8', universal_newlines='\n', capture_output=True)
        print(configure_process.stdout)

        make_process = subprocess.run(['make'], cwd=f"{self.extract_location}", encoding='utf-8', universal_newlines='\n', capture_output=True)
        print(make_process.stdout)

        already_built.touch()


def zlib_build(self) -> None:
    print("="*20)
    print(f"\nBuilding {self.name}")
    print(f"For {self.name} extract location: {self.extract_location}")

    if on_macos:
        zlib_build_macos(self)
    else:
        zlib_build_windows(self)

@register_package
def zlib():
    zlib_version = '1.2.11'
    zlib_version_n = zlib_version.replace('.', '')
    zlib_url = f'https://www.zlib.net/zlib{zlib_version_n}.zip'
    zlib_local = dl_folder / f'zlib_{zlib_version}.zip'
    zlib_dep = Package("zlib", zlib_version, zlib_url, zlib_local,
                            download_and_extract_package,
                            zlib_include_dir, zlib_library_dir, zlib_patch,
                            zlib_build, zlib_package,
                            [], '')
    return zlib_dep

def libpng_include_dir(self) -> str:
    return ""

def libpng_library_dir(self) -> str:
    return ""

def libpng_package(self) -> None:
    pass

def libpng_patch(self):
    patch_file = current_path / 'patches' / 'lpng_build_system.patch'
    patch_file_applied = build_folder / 'lpng_build_system.patch.applied'

    if not patch_file_applied.exists():
        patch_command = [
            'git',
            'apply',
            '--ignore-space-change',
            '--ignore-whitespace',
            '--whitespace=nowarn',
            '-p1',
            f"{patch_file}"
        ]

        patch_process = subprocess.run(patch_command, cwd=self.extract_location, encoding='utf-8', universal_newlines='\n', capture_output=True)
        if patch_process.returncode!=0:
            print(patch_process.stdout)
            raise Exception("Could not patch PNG")
        else:
            print("LibPNG patched.")
        patch_file_applied.touch()
    else:
        print("LibPNG already patched.")

def libpng_macos_build(self) -> None:
    already_built = build_folder / 'libpng.built'
    print("="*20)
    print(f"\nBuilding {self.name}")
    print(f"For {self.name} extract location: {self.extract_location}")
    build_dir = self.extract_location / '..' / 'libpng_build'
    install_dir = self.extract_location / '..' / 'libpng_install'

    if not already_built.exists():
        """dos2unix = [
            "find",
            ".",
            "-type",
            "f",
            "|",
            "xargs",
            "dos2unix"
        ]

        dos2unix_process = subprocess.run(dos2unix, cwd=f"{self.extract_location}", encoding='utf-8', universal_newlines='\n', capture_output=True)

        print(dos2unix_process.stdout)"""

        if build_dir.exists():
            folder_recursive_delete(build_dir)
        build_dir.mkdir()

        if install_dir.exists():
            folder_recursive_delete(install_dir)
        install_dir.mkdir()

        libpng_config_cmake = [
            'cmake',
            '-G',
            'Unix Makefiles' if on_macos else 'Visual Studio 16 2019',
            '-DPNG_TESTS=OFF',
            '-DPNG_SHARED=OFF',
            '-DAWK=/usr/local/bin/gawk',
            f'-DCMAKE_SYSTEM_PREFIX={install_dir}',
            f'-DCMAKE_INSTALL_PREFIX={install_dir}',
            f'{self.extract_location}'
        ]

        libpng_config_process = subprocess.run(libpng_config_cmake, cwd=build_dir, encoding='utf-8', capture_output=True)
        if libpng_config_process.returncode!=0:
            print("Configuring libPNG failed")
            print(libpng_config_process.stdout)
            print(libpng_config_process.stderr)
            raise Exception("Configuring libPNG failed")
        else:
            print("libPNG configured")


        make_process = subprocess.run(['cmake', '--build', '.', '--target', 'install'], cwd=build_dir, encoding='utf-8', universal_newlines='\n', capture_output=True)

        if make_process.returncode!=0:
            print("Building libPNG failed")
            print(make_process.stdout)
            print(make_process.stderr)
            raise Exception("Building libPNG failed")

        already_built.touch()

def libpng_windows_build(self) -> None:
    already_built = build_folder / 'libpng.built'
    print("="*20)
    print(f"\nBuilding {self.name}")
    print(f"For {self.name} extract location: {self.extract_location}")

    sln = self.extract_location / 'projects' / 'vstudio' / 'vstudio.sln'

    build_settings = [f"{msbuild}",
                      f"{sln}",
                      "/t:libpng",
                      "/p:Configuration=Release Library",
                      "/p:Platform=x64",
                      "/m"
    ]

    if not already_built.exists():
        completed_process = subprocess.run(build_settings, encoding='utf-8', universal_newlines='\n', capture_output=True)
        print(completed_process.stdout)
        already_built.touch()

def libpng_build(self) -> None:
    print("="*20)
    print(f"\nBuilding {self.name}")
    print(f"For {self.name} extract location: {self.extract_location}")

    if on_macos:
        libpng_macos_build(self)
    else:
        libpng_windows_build(self)


@register_package
def libpng():
    libpng_version = '1.6.37'
    libpng_version_n = libpng_version.replace('.', '')
    #libpng_url = f'https://downloads.sourceforge.net/project/libpng/libpng16/1.6.37/lpng1637.zip?ts=gAAAAABhcdxHiIQEppu8-oHTz9BTr3p2tJM_DeS4-wTGyGlS-kXzOZEPyiS_chMS85CqLLmKuoeYL0KiRykk2btl3edJf2E_tw%3D%3D&r=https%3A%2F%2Fsourceforge.net%2Fprojects%2Flibpng%2Ffiles%2Flibpng16%2F1.6.37%2Flpng1637.zip%2Fdownload%3Fuse_mirror%3Daltushost-swe'
    
    libpng_url = 'https://downloads.sourceforge.net/project/libpng/libpng16/1.6.37/libpng-1.6.37.tar.gz?ts=gAAAAABhvF0oil3-kb0cblcm84Gl5XI3czxVE87TaeARn56PerrRwPViMRERvr8KKWSi88uy4gmoj9J6ZolV4oQw8CQSDfIf5Q%3D%3D&r=https%3A%2F%2Fsourceforge.net%2Fprojects%2Flibpng%2Ffiles%2Flibpng16%2F1.6.37%2Flibpng-1.6.37.tar.gz%2Fdownload'
    libpng_local = dl_folder / f'libpng_{libpng_version_n}.tar.gz'
    libpng_dep = Package("libpng", libpng_version, libpng_url, libpng_local,
                            download_and_extract_package,
                            libpng_include_dir, libpng_library_dir, libpng_patch,
                            libpng_build, libpng_package,
                            ['zlib'], '')
    return libpng_dep

def embree_include_dir(self) -> str:
    return ""

def embree_library_dir(self) -> str:
    return ""

def embree_package(self) -> None:
    pass

def embree_build(self) -> None:
    print(self.extract_location)
    already_built = build_folder / 'embree.built'
    # we shouldn't build in the source directory (extract_location)
    build_dir = (self.extract_location / '..' / 'embree_build').resolve()
    install_dir = (self.extract_location / '..' / 'embree_install').resolve()
    if not already_built.exists():
        if build_dir.exists():
            folder_recursive_delete(build_dir)
        build_dir.mkdir()

        if install_dir.exists():
            folder_recursive_delete(install_dir)
        install_dir.mkdir()

        tasking_system = 'INTERNAL' if on_macos else 'PPL'

        embree_config_cmake = [
            'cmake',
            '-G',
            'Unix Makefiles' if on_macos else 'Visual Studio 16 2019',
            f'-DCMAKE_SYSTEM_PREFIX={install_dir}',
            f'-DCMAKE_INSTALL_PREFIX={install_dir}',
            '-DEMBREE_LIBRARY_NAME=embree3_RH',
            f'-DEMBREE_TASKING_SYSTEM={tasking_system}', # tbb (thread building blocks), ppl (parallel patterns library, windows only), internal
            '-DEMBREE_ISPC_SUPPORT=OFF',
            '-DEMBREE_TUTORIALS=OFF',
            #'-dopenexr_lib_suffix=-rh-2_5',
            #'-dilmbase_lib_suffix=-rh-2_5',
            f"{self.extract_location}"
        ]

        embree_config_process = subprocess.run(embree_config_cmake, cwd=build_dir, encoding='utf-8', capture_output=True)
        if embree_config_process.returncode!=0:
            print(embree_config_process.stdout)
            print(embree_config_process.stderr)
            raise Exception("embree configuration failed")

        embree_build_cmake = [
            'cmake',
            '--build',
            '.',
            '--target',
            'install',
            '--config',
            'release'
        ]
        embree_build_process = subprocess.run(embree_build_cmake, cwd=build_dir, encoding='utf-8', capture_output=True)
        if embree_build_process.returncode!=0:
            print(embree_build_process.stdout)
            raise Exception("embree build failed")

        already_built.touch()
    else:
        print(f"embree already built")

@register_package
def embree():
    embree_version = '3.13.2'
    embree_url = f'https://github.com/embree/embree/archive/refs/tags/v{embree_version}.zip'
    embree_local = dl_folder / f'embree_{embree_version}.zip'
    embree_dep = Package("embree", embree_version, embree_url, embree_local,
                            download_and_extract_package,
                            embree_include_dir, embree_library_dir, no_patches,
                            embree_build, embree_package,
                            [], '')
    return embree_dep

def libtiff_include_dir(self) -> str:
    install_dir = (Path(self.extract_location) / '..' / 'libtiff_install' / 'include').resolve()
    return f"{install_dir}"

def libtiff_library_dir(self) -> str:
    if on_macos:
        lib = Path(self.extract_location) / '..' / 'libtiff_install' / 'lib' / 'libtiff.a'
    else:
        lib = Path(self.extract_location) / '..' / 'libtiff_install' / 'lib' / 'tiff.lib'
    lib = lib.resolve()
    return f"{lib}"

def libtiff_package(self) -> None:
    pass

def libtiff_patch(self):
    patch_file = current_path / 'patches' / 'libtiff_build_system.patch'
    patch_file_applied = build_folder / 'libtiff_build_system.patch.applied'

    if not patch_file_applied.exists():
        patch_command = [
            'git',
            'apply',
            '--ignore-space-change',
            '--ignore-whitespace',
            '--whitespace=nowarn',
            '-p1',
            f"{patch_file}"
        ]
        patch_process = subprocess.run(patch_command, cwd=self.extract_location, encoding='utf-8', universal_newlines='\n', capture_output=True)
        if patch_process.returncode!=0:
            print(patch_process.stderr)
            print(patch_process.stdout)
            raise Exception("libtiff patching failed.")
        patch_file_applied.touch()
        print("libtiff patch successfully applied.")
    else:
        print("libtiff patch already applied.")
def libtiff_build(self) -> None:
    print(self.extract_location)
    already_built = build_folder / 'libtiff.built'
    # we shouldn't build in the source directory (extract_location)
    build_dir = Path(self.extract_location) / '..' / 'libtiff_build'
    install_dir = Path(self.extract_location) / '..' / 'libtiff_install'

    if not already_built.exists():
        if build_dir.exists():
            folder_recursive_delete(build_dir)
        build_dir.mkdir()

        if install_dir.exists():
            folder_recursive_delete(install_dir)
        install_dir.mkdir()

        for p in packages:
            if p.name.lower() == 'zlib':
                zlib_library = p.get_library_dir(p)
                zlib_include_dir = p.get_include_dir(p)
            if p.name.lower() == 'libjpeg':
                jpeg_library = p.get_library_dir(p)
                jpeg_include_dir = p.get_include_dir(p)

        libtiff_config_cmake = [
            'cmake',
            '-G',
            'Unix Makefiles' if on_macos else 'Visual Studio 16 2019',
            f'-DCMAKE_SYSTEM_PREFIX={install_dir}',
            f'-DCMAKE_INSTALL_PREFIX={install_dir}',
            '-DBUILD_SHARED_LIBS=OFF',
            f'-DZLIB_LIBRARY={zlib_library}',
            f'-DZLIB_INCLUDE_DIR={zlib_include_dir}',
            f'-DJPEG_LIBRARY={jpeg_library}',
            f'-DJPEG_INCLUDE_DIR={jpeg_include_dir}',
            '-Dlerc=OFF',
            '-Dlibdeflate=OFF',
            '-Djbig=OFF',
            '-Djpeg12=OFF',
            '-Dwebp=OFF',
            '-Dzstd=OFF',
            '-DENABLE_WebP=OFF',
            '-DENABLE_WEBP=OFF',
            '-DENABLE_ZSTD=OFF',
            '-DENABLE_JPEG12=OFF',
            '-DENABLE_JBIG=OFF',
            f"{self.extract_location}"
        ]

        libtiff_config_process = subprocess.run(libtiff_config_cmake, cwd=build_dir, encoding='utf-8', capture_output=True)
        if libtiff_config_process.returncode!=0:
            print(libtiff_config_process.stdout)
            print(libtiff_config_process.stderr)
            raise Exception("libtiff configuration failed")

        libtiff_build_cmake = [
            'cmake',
            '--build',
            '.',
            '--target',
            'install',
            '--config',
            'release'
        ]
        libtiff_build_process = subprocess.run(libtiff_build_cmake, cwd=build_dir, encoding='utf-8', capture_output=True)
        if libtiff_build_process.returncode!=0:
            print(libtiff_build_process.stdout)
            raise Exception("libtiff build failed")

        already_built.touch()
    else:
        print(f"libtiff already built")

@register_package
def libtiff():
    libtiff_version = '4.3.0'
    libtiff_url = f'https://gitlab.com/libtiff/libtiff/-/archive/v{libtiff_version}/libtiff-v{libtiff_version}.zip'
    libtiff_local = dl_folder / f'libtiff_{libtiff_version}.zip'
    libtiff_dep = Package("libtiff", libtiff_version, libtiff_url, libtiff_local,
                            download_and_extract_package,
                            libtiff_include_dir, libtiff_library_dir, libtiff_patch,
                            libtiff_build, libtiff_package,
                            ['libjpeg'], '')
    return libtiff_dep

def libjpeg_include_dir(self) -> str:
    install_dir = (Path(self.extract_location) / '..' / 'libjpeg_install' / 'include').resolve()
    return f"{install_dir}"

def libjpeg_library_dir(self) -> str:
    if on_macos:
        lib = Path(self.extract_location) / '..' / 'libjpeg_install' / 'lib' / 'libjpeg.a'
    else:
        lib = Path(self.extract_location) / '..' / 'libjpeg_install' / 'lib' / 'jpeg.lib'
    lib = lib.resolve()
    return f"{lib}"

def libjpeg_package(self) -> None:
    pass

def libjpeg_build(self) -> None:
    print(self.extract_location)
    already_built = build_folder / 'libjpeg.built'
    # we shouldn't build in the source directory (extract_location)
    build_dir = Path(self.extract_location) / '..' / 'libjpeg_build'
    install_dir = Path(self.extract_location) / '..' / 'libjpeg_install'

    if not already_built.exists():
        if build_dir.exists():
            folder_recursive_delete(build_dir)
        build_dir.mkdir()

        if install_dir.exists():
            folder_recursive_delete(install_dir)
        install_dir.mkdir()

        libjpeg_config_cmake = [
            'cmake',
            '-G',
            'Unix Makefiles' if on_macos else 'Visual Studio 16 2019',
            f'-DCMAKE_SYSTEM_PREFIX={install_dir}',
            f'-DCMAKE_INSTALL_PREFIX={install_dir}',
            f"{self.extract_location}"
        ]

        libjpeg_config_process = subprocess.run(libjpeg_config_cmake, cwd=build_dir, encoding='utf-8', capture_output=True)
        if libjpeg_config_process.returncode!=0:
            print(libjpeg_config_process.stdout)
            print(libjpeg_config_process.stderr)
            raise Exception("libjpeg configuration failed")

        libjpeg_build_cmake = [
            'cmake',
            '--build',
            '.',
            '--target',
            'install',
            '--config',
            'release'
        ]
        libjpeg_build_process = subprocess.run(libjpeg_build_cmake, cwd=build_dir, encoding='utf-8', capture_output=True)
        if libjpeg_build_process.returncode!=0:
            print(libjpeg_build_process.stdout)
            raise Exception("libjpeg build failed")

        already_built.touch()
    else:
        print(f"libjpeg already built")

@register_package
def libjpeg():
    libjpeg_version = '2.1.1'
    libjpeg_url = f'https://github.com/libjpeg-turbo/libjpeg-turbo/archive/refs/tags/{libjpeg_version}.zip'
    libjpeg_local = dl_folder / f'libjpeg_{libjpeg_version}.zip'
    libjpeg_dep = Package("libjpeg", libjpeg_version, libjpeg_url, libjpeg_local,
                            download_and_extract_package,
                            libjpeg_include_dir, libjpeg_library_dir, no_patches,
                            libjpeg_build, libjpeg_package,
                            [], '')
    return libjpeg_dep

G = [copy.deepcopy(p) for p in packages]
S = [copy.deepcopy(p) for p in G if len(p.dependencies)==0]
for p in S:
    p.dependencies = [d.lower() for d in p.dependencies]
L : List[Package] = list()
while len(S)>0:
    n = S.pop(0)
    L.append(n)
    for m in G:
        if n.name.lower() in m.dependencies:
            m.dependencies.remove(n.name.lower())
            if len(m.dependencies)==0:
                S.append(m)

_packages = {p.name: p for p in packages}
packages = [_packages[p.name] for p in L]

incomplete_packages = [p for p in G if len(p.dependencies)>0]
if len(incomplete_packages)>0:
    print("The following packages have missing dependencies:")
    for ip in incomplete_packages:
        print(f"{ip.name} - {ip.dependencies!r}")
    sys.exit(13)

for package in packages:
    print(f"Fetching {package.name}...")
    package.acquire_it()
    print(f"Patching {package.name}...")
    package.patch_it()
    print(f"Building {package.name}...")
    package.build_it()
    print(f"{package.name} ready")

