"""Package project sources/resources and optionally export the clean AMD64 image.

python docker/package.py --output ../deliverables/anamnesis-amd64 --export-image
Personal state is never copied from a running container or its data mounts.
"""
import argparse
import gzip
import hashlib
import json
import shutil
import subprocess
import tarfile
import time
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERSION = '2026.10.31'
IMAGE = 'anamnesis:'+VERSION+'-full'
SOURCE = 'anamnesis-'+VERSION+'-source-resources.zip'
IMAGE_FILE = 'anamnesis-'+VERSION+'-linux-amd64.tar.gz'
SKIP_DIRS = {'.git', '.venv', 'venv', 'node_modules', '__pycache__', '.pytest_cache',
    '.mypy_cache', '.ruff_cache', '.cache', '.local', '.venv-local', '.venv-openwebui', 'vendor', 'dist', 'build', 'tests', 'test-results',
    'playwright-report', 'htmlcov', 'docker-data', '.local-preview'}
SKIP_FILES = {'.DS_Store', 'Thumbs.db', '.env', '.apikey', '.session-secret',
    '.webui_secret_key', '.coverage', 'coverage.xml', 'accounts.db', 'webui.db',
    'words.db', '交付使用说明.md', '.password', '.secret_key', '.api_token', 'SHA256SUMS.txt', 'release-manifest.json'}
REQUIRED = ['Dockerfile', '.dockerignore', 'compose.yaml', 'compose.image.yaml',
    '.env.example', '部署生产.sh', '验收记录-20261031.md', 'docker/prepare_runtime.py', 'docker/entrypoint.py', 'docker/seed_cache.py',
    'docker/search-requirements.txt', 'docker/embedding-requirements.txt',
    'docker/embedding_model.py', '英语单词/web_server.py', '英语单词/requirements.txt',
    '朗文英汉/oaldpe.mdx', '英语单词/resources/lexicons/lexicons.sqlite3',
    '英语单词/resources/lexicons/wordnet.zip']


def keep(relative):
    if relative.parts[0] not in {'英语单词','朗文英汉','docker'} and len(relative.parts)>1:
        return False
    if any(part in SKIP_DIRS or part.startswith('.venv') for part in relative.parts):
        return False
    if len(relative.parts)>1 and relative.parts[0]=='英语单词' and relative.parts[1] in ('data','dict'):
        return False
    name = relative.name
    if name in {'audit_live.py','verify_live_socket.py','compose.macos-chat.yaml'}:
        return False
    if name in SKIP_FILES or name.startswith(('test_', '.env.', '.apikey-', '.session-secret')):
        return name == '.env.example'
    return not (relative.suffix.lower() in {'.pyc','.pyo','.log','.tmp','.bak','.download','.part'}
        or name.endswith(('.build.sqlite3','.db-wal','.db-shm','.sqlite3-wal','.sqlite3-shm')))


def digest(path):
    value = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda:stream.read(8*1024*1024), b''):
            value.update(chunk)
    return value.hexdigest()


def readme():
    return f'''# 忆溯完整版源码与 AMD64 镜像交付

镜像：`{IMAGE}`；平台：`linux/amd64`，适用于 Intel/AMD x86-64 Linux 容器。

本次交付源码与生产自动构建配置，未附 Docker 镜像归档。请先解压源码，在解压目录配置 `.env`，然后执行 `sh 部署生产.sh`。同目录单独提供的 Compose 和脚本仅供查看或复制，构建必须在含 Dockerfile 的完整源码目录执行。

## 后续取得镜像归档时运行

```sh
docker load -i {IMAGE_FILE}
docker compose -f compose.image.yaml up -d
```

新安装先将 `.env.example` 复制为 `.env`，按实际入口设置 APP_PUBLIC_URL、APP_PORT 和数据目录。已有安装继续使用原 `.env` 和数据目录，不覆盖已有配置；保留数据目录中的隐藏密钥文件，避免账号会话失效。升级前停止旧容器并备份完整数据。`compose.image.yaml` 不包含 build；加载镜像后无需下载基础镜像和软件依赖，缺失模型仍可能在启动时联网补齐。

本次验收范围与限制见源码内《验收记录-20261031.md》。默认入口 `http://localhost:5050/words/`。平台登录后自动进入集成 OpenWebUI，无需二次密码；MCP、免密钥网络搜索、本地 embedding/Chroma、每轮后台自动提炼与跨对话记忆均按项目默认接入。同一账号的不同助手共享记忆。搜索需要互联网，聊天与记忆提炼使用所配置的聊天模型。

## 源码与资源

`{SOURCE}` 包含本项目 Python/前端源码、Docker 构建与部署文件、本地 MDX 词典、ECDICT/分类 SQLite、WordNet、词表、图标及说明/来源许可。词库 SQLite 是只读运行资源，已保留；个人用户数据库不包含在交付中。

已排除缓存、测试套件/报告、虚拟环境、系统杂项、个人数据与真实配置/密钥；保留健康检查和部署诊断脚本。清理只作用于交付包，不删除开发目录或现有用户数据。

源码解压后可运行 `docker compose build` 构建，构建需要联网获取固定基础镜像、软件依赖和指定版本模型。源码包不是离线编译工具链。第三方 OpenWebUI 和软件依赖通过 Dockerfile 引用，上游版本和 digest 已固定，没有混入第三方完整开发仓库。

本次先交付源码与生产自动构建配置，未附镜像归档；不要把源码包当作已验收的 AMD64 镜像。执行 `sh 部署生产.sh` 会下载固定的完整版基础镜像并构建 linux/amd64。系统依赖在构建时安装；本地向量模型默认在构建时下载，缺失模型会在启动时补齐到持久缓存，下载失败不会误报健康。完整版 OCR、Chromium、Office、Whisper 和记忆能力需在目标服务器完成实机验收。图像生成、其他语音/重排模型、云服务和 GPU 推理仍取决于各自模型、服务或硬件配置；这是标准 CPU 完整版。

## 校验

`SHA256SUMS.txt` 和 `release-manifest.json` 记录大小、SHA-256、镜像 ID 与架构。Linux 可用 `sha256sum -c SHA256SUMS.txt`，Windows 可用 `Get-FileHash 文件名 -Algorithm SHA256` 比对。ZIP 已检查 CRC、必须资源和排除项；本次没有镜像归档，未执行镜像 manifest 或运行验收；后续使用 --export-image 时才执行这些检查。

第三方资源的来源及许可说明位于源码资源目录，请保留。更详细部署说明见源码中的《DOCKER部署说明.md》。
'''


def export_image(docker, output):
    temporary = output.with_name(output.name+'.part')
    process = subprocess.Popen([docker,'image','save','--platform=linux/amd64',IMAGE], stdout=subprocess.PIPE)
    try:
        last, count = time.monotonic(), 0
        with temporary.open('wb') as raw:
            with gzip.GzipFile(filename='',mode='wb',fileobj=raw,compresslevel=1,mtime=0) as compressed:
                while chunk := process.stdout.read(4*1024*1024):
                    compressed.write(chunk)
                    count += len(chunk)
                    if time.monotonic()-last >= 30:
                        print('Image export: %.2f GiB streamed' % (count/1024**3),flush=True)
                        last = time.monotonic()
        if process.wait() != 0:
            raise RuntimeError('Docker export failed')
        temporary.replace(output)
    finally:
        if process.poll() is None:
            process.terminate()
        process.stdout.close()


def verify_image(path):
    docs, layers = {}, set()
    # Stream through EOF without extracting arbitrary paths or retaining layers.
    with tarfile.open(path,'r|gz') as archive:
        for member in archive:
            if member.isfile():
                layers.add(member.name)
            if member.isfile() and member.size < 2*1024*1024:
                if member.name in ('manifest.json','index.json','oci-layout') or member.name.endswith('.json') or member.name.startswith('blobs/sha256/'):
                    try:
                        docs[member.name] = json.loads(archive.extractfile(member).read())
                    except (UnicodeError,ValueError):
                        pass
    manifest = docs.get('manifest.json')
    if not manifest:
        raise RuntimeError('Missing Docker archive manifest')
    entry = next(item for item in manifest if IMAGE in (item.get('RepoTags') or []))
    config = docs[entry['Config']]
    assert config['os']=='linux' and config['architecture']=='amd64'
    assert entry['Layers'] and set(entry['Layers']).issubset(layers)
    # Consume the gzip footer too, so a truncated final block is rejected.
    with gzip.open(path,'rb') as stream:
        while stream.read(16*1024*1024):
            pass
    return {'platform':'linux/amd64','layers':len(entry['Layers'])}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=ROOT/'dist')
    parser.add_argument('--export-image',action='store_true')
    parser.add_argument('--docker',default='docker')
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True,exist_ok=True)
    files = []
    import os
    for directory, dirs, names in os.walk(ROOT):
        parent = Path(directory)
        dirs[:] = [name for name in dirs if keep((parent/name).relative_to(ROOT)) and output not in (parent/name).parents and parent/name != output]
        for name in names:
            path = parent/name
            if not path.is_symlink() and keep(path.relative_to(ROOT)):
                files.append(path)
    found = {p.relative_to(ROOT).as_posix() for p in files}
    if missing := set(REQUIRED)-found:
        raise RuntimeError('Required files missing: '+str(sorted(missing)))
    source = output/SOURCE
    with zipfile.ZipFile(source,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as archive:
        for path in sorted(files):
            archive.write(path,path.relative_to(ROOT).as_posix())
        archive.writestr('交付使用说明.md',readme())
    with zipfile.ZipFile(source) as archive:
        assert archive.testzip() is None
        assert len(archive.namelist()) == len(set(archive.namelist()))
        assert all(name == '交付使用说明.md' or keep(Path(name)) for name in archive.namelist())
        assert set(REQUIRED).issubset(archive.namelist())
    print('PASS source ZIP: %d project files, required resources included, cache/tests/private state excluded' % len(files),flush=True)
    for name in ('compose.image.yaml','compose.yaml','.env.example','部署生产.sh'):
        shutil.copyfile(ROOT/name,output/name)
    (output/'使用说明.md').write_text(readme(),encoding='utf-8')
    info = {}
    if args.export_image:
        inspect = json.loads(subprocess.check_output([args.docker,'image','inspect','--platform=linux/amd64',IMAGE]))[0]
        assert inspect['Os']=='linux' and inspect['Architecture']=='amd64'
        info = {'tag':IMAGE,'id':inspect['Id'],'unpacked_bytes':inspect['Size']}
        export_image(args.docker,output/IMAGE_FILE)
        info.update(verify_image(output/IMAGE_FILE))
        print('PASS Docker archive: linux/amd64 manifest, all layers and gzip verified',flush=True)
    artifacts = [source,output/'compose.image.yaml',output/'compose.yaml',output/'部署生产.sh',output/'.env.example',output/'使用说明.md']
    if args.export_image:
        artifacts.append(output/IMAGE_FILE)
    records = [{'file':p.name,'bytes':p.stat().st_size,'sha256':digest(p)} for p in artifacts]
    (output/'SHA256SUMS.txt').write_text(''.join(row['sha256']+'  '+row['file']+'\n' for row in records),encoding='utf-8')
    (output/'release-manifest.json').write_text(json.dumps({'version':VERSION,'image':info,
        'source_file_count':len(files)+1,'artifacts':records},ensure_ascii=False,indent=2),encoding='utf-8')
    for row in records:
        print('%s: %.2f MiB' % (row['file'],row['bytes']/1024**2),flush=True)
    print('Delivery directory:',output,flush=True)


if __name__ == '__main__':
    main()
