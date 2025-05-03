# KoeMemo Windows セットアップガイド

このガイドでは、Windows環境でのKoeMemo（コエメモ）のインストールから初期設定までの詳細な手順を説明します。

## 目次

1. [前提条件](#前提条件)
2. [インストール手順](#インストール手順)
   - [開発者モードの有効化](#開発者モードの有効化)
   - [Pythonのインストール](#pythonのインストール)
   - [KoeMemoのダウンロード](#koememoのダウンロード)
   - [FFmpegのインストール](#ffmpegのインストール)
   - [必要なPythonライブラリのインストール](#必要なpythonライブラリのインストール)
3. [初期設定](#初期設定)
4. [KoeMemoの起動](#koememoの起動)
5. [トラブルシューティング](#トラブルシューティング)

## 前提条件

KoeMemoをWindows環境で使用するには、以下のソフトウェアが必要です：

- Python 3.9以上（3.11.3推奨、FasterWhisperの要件により3.8では動作しません）
- FFmpeg
- インターネット接続（初回のモデルダウンロードとLLM API連携用）

## インストール手順

### 開発者モードの有効化

**この手順は必須です。特にLargeモデルを使用する場合は省略できません。**

1. スタートメニュー → 「設定」（歯車アイコン）をクリック
2. 「更新とセキュリティ」 → 「開発者向け」を選択
3. 「開発者モード」をオンにする
4. 確認ダイアログが表示されたら「はい」をクリック
5. 変更が適用されるまで待機

### Pythonのインストール

1. [Python公式サイト](https://www.python.org/downloads/windows/)からPython 3.9以上をダウンロード（3.11.3推奨）
   - 過去バージョンは[Downloads](https://www.python.org/downloads/)ページで「Looking for a specific release?」から選択
   - [Python 3.11.3](https://www.python.org/downloads/release/python-3113/)を選択し、Windows installerをダウンロード
2. インストーラを実行する
   - **重要**: 「Add Python to PATH」にチェックを入れる
   - 「Install Now」をクリック
3. インストール完了後、コマンドプロンプトで確認:
   ```
   python --version
   ```

**注意**: FasterWhisperの要件により、Python 3.8では動作しません。Python 3.9以上が必要で、3.11.3の使用を推奨します。

### KoeMemoのダウンロード

1. GitHubからリポジトリをクローン:
   ```
   git clone https://github.com/yourusername/koememo.git
   ```
   または、ZIPファイルとしてダウンロードして任意の場所に解凍

2. ダウンロードしたフォルダを覚えておいてください（例: `C:\Users\username\Downloads\koememo`）

### FFmpegのインストール

1. [gyan.dev](https://www.gyan.dev/ffmpeg/builds/)からWindows用のFFmpegをダウンロード
   - 例：「ffmpeg-release-essentials.zip」を選択

2. ダウンロードしたファイルを解凍（7-Zipなどが必要）
   - 適当な場所に解凍（例: `C:\ffmpeg`）

3. 環境変数のPATHにFFmpegの「bin」ディレクトリを追加:
   - スタートメニュー → 「環境変数」と検索 → 「システム環境変数の編集」
   - 「環境変数」ボタンをクリック
   - 「システム環境変数」の「Path」を選択して「編集」
   - 「新規」をクリックし、FFmpegの「bin」ディレクトリのフルパスを追加（例: `C:\ffmpeg\bin`）
   - 「OK」をクリックして全ての画面を閉じる

4. コマンドプロンプトを再起動し、以下のコマンドでFFmpegが正しくインストールされたか確認:
   ```
   ffmpeg -version
   ```

### 必要なPythonライブラリのインストール

1. コマンドプロンプトを管理者権限で実行
2. KoeMemoのディレクトリに移動:
   ```
   cd C:\Users\username\Downloads\koememo
   ```
3. 以下のコマンドを一行ずつ実行して必要なライブラリをインストール:

   ```
   pip install huggingface-hub
   ```

   ```
   pip install faster-whisper
   ```

   ```
   pip install requests
   ```

   ```
   pip install watchdog
   ```

**注意**:
- コマンドは一行ずつ実行することで、エラーの発見と対処が容易になります
- FasterWhisperはPython 3.9以上を要求しており、3.8では動作しません
- インストール中にエラーが発生した場合は、[トラブルシューティング](#トラブルシューティング)セクションを参照してください

## 初期設定

KoeMemoを初めて起動すると、設定画面が表示されます。以下の手順で初期設定を行います。

### ディレクトリ設定

「基本設定」タブで以下のディレクトリを設定します：

1. **入力ディレクトリ**:
   - 処理したい音声・動画ファイルを置くフォルダを指定します
   - 「参照...」ボタンをクリックして選択するか、直接パスを入力します
   - 例: `C:\Users\username\Documents\KoeMemo\input`

2. **文字起こしディレクトリ**:
   - 文字起こし結果を保存するフォルダを指定します
   - 「参照...」ボタンをクリックして選択するか、直接パスを入力します
   - 例: `C:\Users\username\Documents\KoeMemo\transcripts`

3. **出力ディレクトリ**:
   - 生成された議事録を保存するフォルダを指定します
   - 「参照...」ボタンをクリックして選択するか、直接パスを入力します
   - 例: `C:\Users\username\Documents\KoeMemo\output`

**注意**: すべてのディレクトリが存在しない場合は、自動的に作成されますが、作成先の親ディレクトリに対する書き込み権限が必要です。

### 文字起こしモデル設定

「モデル設定」タブで以下の設定を行います：

1. **モデルサイズ**:
   - 小さいほど処理速度が速く、大きいほど精度が高くなります
   - 低性能PCの場合は「tiny」を選択
   - 標準的なPCであれば「base」または「small」を選択
   - 高性能PCまたはGPU搭載PCの場合は「medium」または「large」を選択
   - **重要**: 「large」モデルを使用する場合は、必ず開発者モードをオンにしてください

2. **言語**:
   - 日本語音声の場合は「日本語」
   - 英語音声の場合は「英語」
   - 複数の言語が混在する場合は「自動検出」

3. **計算タイプ**:
   - CPU環境では「int8」を選択（デフォルト）
   - GPU環境では「float16」を選択可能

### LLM API設定

「LLM設定」タブで以下の設定を行います：

1. **API種類**:
   - 使用するLLMサービスを選択（OpenAI、Anthropic、Google）

2. **APIキー**:
   - 選択したサービスのAPIキーを入力

3. **モデル**:
   - 使用するモデルを選択
   - OpenAIの場合の推奨: `gpt-3.5-turbo`（低コスト）または `gpt-4o`（高品質）

4. **Temperature**:
   - 議事録生成には0.2〜0.4が推奨

5. **最大トークン数**:
   - 1000〜2000が一般的な設定

## KoeMemoの起動

1. KoeMemoフォルダに移動
2. `start.bat` をダブルクリック
   または、コマンドプロンプトで以下を実行:
   ```
   python gui.py
   ```
3. GUIが起動したら、「基本設定」タブですべてのディレクトリが正しく設定されていることを確認
4. 画面下部の「サービス開始」ボタンをクリック
5. サービスが正常に開始されると、ステータスが「サービスは実行中です」に変わります

## トラブルシューティング

### 開発者モードに関する問題

- Windows 10: 「設定」→「更新とセキュリティ」→「開発者向け」で開発者モードを有効にします
- Windows 11: 「設定」→「プライバシーとセキュリティ」→「開発者向け」で開発者モードを有効にします

### Pythonのインストールに関する問題

- PATHが正しく設定されていない場合:
  1. 「システム環境変数」を開く
  2. 「Path」変数を編集し、Pythonのインストールディレクトリとそのサブディレクトリ「Scripts」が含まれていることを確認
  3. 例: `C:\Users\username\AppData\Local\Programs\Python\Python311` および `C:\Users\username\AppData\Local\Programs\Python\Python311\Scripts`

### FFmpegのインストールに関する問題

- PATHが正しく設定されていない場合:
  1. 「システム環境変数」を開く
  2. 「Path」変数を編集し、FFmpegの「bin」ディレクトリが含まれていることを確認
  3. 例: `C:\ffmpeg\bin`

### ライブラリのインストールエラー

- Faster-Whisperのインストールでエラーが発生する場合:
  1. Visual C++ Build Toolsをインストール:
     - [Visual Studio Build Tools](https://visualstudio.microsoft.com/visual-cpp-build-tools/)をダウンロード
     - インストーラを実行し、「C++ Build Tools」を選択してインストール
  2. Hugging Faceライブラリを先にインストールしてから再試行:
     ```
     pip install huggingface-hub
     pip install faster-whisper
     ```

### その他の問題

- Python 3.9以上（3.11.3推奨）が正しくインストールされているか確認してください
- Windows Defenderやウイルス対策ソフトが実行を妨げている可能性があります。必要に応じて例外設定を行ってください
- コマンドプロンプトを管理者権限で実行してコマンドを試してみてください