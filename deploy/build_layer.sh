#!/bin/bash
# Lambda Layer構築スクリプト（Docker版）
# Amazon Linux 2023環境でビルドしてLinuxバイナリを生成

set -e

echo "================================================================================"
echo "Lambda Layer構築を開始します（Docker使用）"
echo "================================================================================"

# プロジェクトルートに移動
cd "$(dirname "$0")/.."

# Dockerの存在確認
if ! command -v docker &> /dev/null; then
    echo "❌ エラー: Dockerがインストールされていません"
    echo "   以下のURLからDockerをインストールしてください:"
    echo "   https://docs.docker.com/get-docker/"
    exit 1
fi

# Dockerデーモンの起動確認
if ! docker info &> /dev/null; then
    echo "❌ エラー: Dockerデーモンが起動していません"
    echo "   Docker Desktopを起動してください"
    exit 1
fi

# 作業ディレクトリをクリーンアップ
echo "既存の作業ディレクトリをクリーンアップ"
rm -rf layer lambda-layer.zip

# 作業ディレクトリ作成
echo "作業ディレクトリを作成"
mkdir -p layer

# requirements-lambda.txtの存在確認
if [ ! -f "requirements-lambda.txt" ]; then
    echo "❌ エラー: requirements-lambda.txt が見つかりません"
    exit 1
fi

# Dockerfileの存在確認
if [ ! -f "deploy/Dockerfile.layer" ]; then
    echo "❌ エラー: deploy/Dockerfile.layer が見つかりません"
    exit 1
fi

# Dockerイメージをビルド（x86_64プラットフォームを明示的に指定）
echo "Dockerイメージをビルド中（x86_64/amd64プラットフォーム）..."
docker build --platform linux/amd64 -f deploy/Dockerfile.layer -t lambda-layer-builder .

# Dockerコンテナを実行してパッケージをビルド（x86_64プラットフォームを明示的に指定）
echo "Dockerコンテナ内で依存パッケージをビルド中..."
docker run --platform linux/amd64 --rm -v "$(pwd)/layer:/output" lambda-layer-builder \
  bash -c "cp -r /build/python /output/"

# ビルド結果を確認
if [ ! -d "layer/python" ]; then
    echo "❌ エラー: ビルドに失敗しました"
    exit 1
fi

echo "✓ Dockerビルド完了"

# バイナリが正しくLinux x86_64形式か確認
echo ""
echo "バイナリアーキテクチャを確認中..."
so_files=$(find layer/python -name "*.so" -type f | head -5)
if [ -n "$so_files" ]; then
    echo "サンプル .so ファイル:"
    echo "$so_files" | while read -r file; do
        arch=$(file "$file" | grep -o "x86-64\|x86_64\|ELF 64-bit LSB" || echo "不明")
        if [[ "$arch" == *"x86"* ]] || [[ "$arch" == *"ELF"* ]]; then
            echo "  ✓ $file: Linux x86_64"
        else
            echo "  ⚠️  $file: $arch（要確認）"
        fi
    done
else
    echo "  （.soファイルなし - Pure Pythonパッケージのみ）"
fi

# サイズ確認
echo ""
echo "ディレクトリサイズを確認中..."
layer_size=$(du -sh layer/python | cut -f1)
echo "展開後サイズ: $layer_size"

# Lambda Layer用にzipファイル作成
echo ""
echo "Lambda Layer zipファイルを作成中..."
cd layer
zip -r ../lambda-layer.zip python/ -q
cd ..

# ファイルサイズを表示
zip_size=$(du -h lambda-layer.zip | cut -f1)
zip_size_mb=$(du -m lambda-layer.zip | cut -f1)

echo "================================================================================"
echo "Lambda Layer作成完了"
echo "ファイル: lambda-layer.zip"
echo "サイズ: $zip_size"
echo "================================================================================"

# サイズ判定
if [ $zip_size_mb -le 40 ]; then
    echo "✓ サイズ最適化成功: ${zip_size_mb}MB（目標40MB以下）"
elif [ $zip_size_mb -le 50 ]; then
    echo "⚠️  直接アップロード可能ですが、さらなる最適化を推奨: ${zip_size_mb}MB"
else
    echo "⚠️  警告: Lambda Layerのサイズが50MBを超えています（${zip_size_mb}MB）"
    echo "   S3経由でアップロードする必要があります"
fi

echo ""
echo "次のステップ:"
echo "  1. AWS CLIでLambda Layerを公開:"
if [ $zip_size_mb -le 50 ]; then
    echo "     aws lambda publish-layer-version \\"
    echo "       --layer-name gemini-news-analyzer-dependencies \\"
    echo "       --zip-file fileb://lambda-layer.zip \\"
    echo "       --compatible-runtimes python3.11 \\"
    echo "       --region ap-northeast-1"
else
    echo "     # S3にアップロード"
    echo "     aws s3 cp lambda-layer.zip s3://gemini-news-analyzer/layers/lambda-layer.zip"
    echo ""
    echo "     # S3からLambda Layerを公開"
    echo "     aws lambda publish-layer-version \\"
    echo "       --layer-name gemini-news-analyzer-dependencies \\"
    echo "       --content S3Bucket=gemini-news-analyzer,S3Key=layers/lambda-layer.zip \\"
    echo "       --compatible-runtimes python3.11 \\"
    echo "       --region ap-northeast-1"
fi
echo ""
echo "  2. または deploy.sh を実行してLambda関数と一緒にデプロイ"
