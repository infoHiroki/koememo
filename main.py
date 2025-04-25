#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
KoeMemo - 音声・動画ファイルから自動的に議事録を生成するツール
バックグラウンドサービスとして動作し、指定フォルダを監視して新しいファイルを自動処理します。

主な機能:
- ファイル監視（watchdog）
- 文字起こし（faster-whisper）
- LLM API連携（OpenAI APIなど）
- 議事録生成と保存
"""

import os
import sys
import json
import time
import logging
import threading
import subprocess
import hashlib
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
import queue
import re

# サードパーティライブラリのインポート（必要に応じてインストール）
try:
    from faster_whisper import WhisperModel
except ImportError:
    print("エラー: faster-whisperモジュールがインストールされていません。")
    print("pip install faster-whisper を実行してインストールしてください。")
    sys.exit(1)

try:
    import requests
except ImportError:
    print("エラー: requestsモジュールがインストールされていません。")
    print("pip install requests を実行してインストールしてください。")
    sys.exit(1)

try:
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler, FileCreatedEvent
except ImportError:
    print("エラー: watchdogモジュールがインストールされていません。")
    print("pip install watchdog を実行してインストールしてください。")
    sys.exit(1)

# ロガーの設定
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("koememo.log", encoding="utf-8")
    ]
)
logger = logging.getLogger("koememo")

# 設定ファイルのパス
CONFIG_PATH = Path(__file__).parent / "config.json"

# グローバル変数
whisper_model = None
file_queue = queue.Queue()
processing_thread = None
observer = None
should_stop = False
config = None  # グローバル設定変数


class MediaFileHandler(FileSystemEventHandler):
    """監視フォルダ内のファイル作成イベントを処理するクラス"""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.supported_extensions = config["file_watcher"]["supported_extensions"]
    
    def on_created(self, event):
        """ファイル作成イベントの処理"""
        if not event.is_directory:
            file_path = event.src_path
            ext = os.path.splitext(file_path)[-1].lower()
            
            if ext in self.supported_extensions:
                logger.info(f"新しいメディアファイルを検出: {file_path}")
                
                # ファイルのアクセスが可能になるまで少し待機（他プロセスによる書き込み完了待ち）
                time.sleep(1)
                
                # 処理済みかどうかをチェック
                if is_file_processed(file_path):
                    logger.info(f"ファイルは既に処理済みです: {file_path}")
                    return
                
                file_queue.put(file_path)


def get_file_hash(file_path: str) -> str:
    """ファイルのハッシュ値を計算（ファイルサイズとパスの組み合わせ）"""
    # 高速化のためにファイルサイズとパスの組み合わせをハッシュ
    try:
        file_size = os.path.getsize(file_path)
        hash_input = f"{file_path}:{file_size}"
        return hashlib.md5(hash_input.encode()).hexdigest()
    except Exception as e:
        logger.error(f"ファイルハッシュ計算エラー: {e}")
        # エラーが発生した場合はパスのみからハッシュを生成
        return hashlib.md5(file_path.encode()).hexdigest()


def is_file_processed(file_path: str) -> bool:
    """ファイルが既に処理済みかどうかをチェック"""
    global config
    
    # ファイルハッシュを計算
    file_hash = get_file_hash(file_path)
    
    # 処理済みファイルリストをチェック
    processed_files = config.get("processed_files", {})
    
    # ファイルパスまたはハッシュが一致する場合は処理済み
    return file_path in processed_files or file_hash in processed_files


def mark_file_as_processed(file_path: str, output_file: str):
    """ファイルを処理済みとしてマーク"""
    global config
    
    # ファイルハッシュを計算
    file_hash = get_file_hash(file_path)
    
    # 処理情報を記録
    processed_info = {
        "processed_at": datetime.now().isoformat(),
        "output_file": output_file
    }
    
    # 設定ファイルに追加
    if "processed_files" not in config:
        config["processed_files"] = {}
    
    # ハッシュ値をキーとして保存
    config["processed_files"][file_hash] = processed_info
    
    # 設定を保存
    save_config(config)
    logger.info(f"ファイルを処理済みリストに追加しました: {file_path}")


def load_config() -> Dict[str, Any]:
    """設定ファイルの読み込み"""
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            config_data = json.load(f)
            
            # 設定バージョンチェック
            if "config_version" not in config_data:
                config_data["config_version"] = "1.0.0"
            
            # 処理済みファイルセクションがなければ追加
            if "processed_files" not in config_data:
                config_data["processed_files"] = {}
            
            return config_data
    except (FileNotFoundError, json.JSONDecodeError) as e:
        logger.error(f"設定ファイルの読み込みエラー: {e}")
        sys.exit(1)


def save_config(config: Dict[str, Any]):
    """設定ファイルの保存"""
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=4)


def clean_old_processed_files(max_entries: int = 1000, days_to_keep: int = 30):
    """古い処理済みファイル情報をクリーンアップ"""
    global config
    
    processed_files = config.get("processed_files", {})
    if not processed_files:
        return
    
    # エントリ数が上限を超えている場合、または古いエントリがある場合にクリーンアップ
    if len(processed_files) > max_entries:
        logger.info(f"処理済みファイルリストのクリーンアップを実行します (現在: {len(processed_files)} エントリ)")
        
        # 日付でソート
        sorted_entries = sorted(
            processed_files.items(),
            key=lambda x: x[1].get("processed_at", ""),
            reverse=True
        )
        
        # 上限数まで削減
        config["processed_files"] = dict(sorted_entries[:max_entries])
        save_config(config)
        logger.info(f"処理済みファイルリストを {len(processed_files)} から {len(config['processed_files'])} エントリに削減しました")


def load_whisper_model(config: Dict[str, Any]) -> Optional[WhisperModel]:
    """WhisperModelをロード"""
    try:
        model_config = config["transcription"]
        model_size = model_config["model_size"]
        compute_type = model_config["compute_type"]
        
        logger.info(f"モデル '{model_size}' をロード中...")
        
        # CUDAが利用可能ならGPUを使用
        device = "cuda" if is_cuda_available() else "cpu"
        
        # CPUでfloat16を指定された場合はint8に自動変換
        if device == "cpu" and compute_type == "float16":
            compute_type = "int8"
            logger.info("CPUでの実行のため、計算タイプをint8に自動変更しました。")
        
        model = WhisperModel(
            model_size_or_path=model_size,
            device=device,
            compute_type=compute_type
        )
        
        logger.info(f"モデル '{model_size}' のロードが完了しました。({device}、{compute_type})")
        return model
    
    except Exception as e:
        logger.error(f"モデルのロードエラー: {e}")
        return None


def is_cuda_available() -> bool:
    """CUDAが利用可能かどうかを確認"""
    try:
        import torch
        return torch.cuda.is_available()
    except ImportError:
        return False


def check_ffmpeg() -> bool:
    """FFmpegがインストールされているか確認"""
    try:
        result = subprocess.run(["ffmpeg", "-version"], capture_output=True, text=True)
        return result.returncode == 0
    except FileNotFoundError:
        return False


def transcribe_file(file_path: str, config: Dict[str, Any]) -> Optional[str]:
    """ファイルの文字起こし処理"""
    global whisper_model
    
    try:
        # モデルが未ロードの場合はロード
        if whisper_model is None:
            whisper_model = load_whisper_model(config)
            if whisper_model is None:
                return None
        
        # 言語設定
        language = config["transcription"]["language"]
        if language == "auto":
            language = None  # Whisperの自動検出を使用
            logger.info("言語は自動検出を使用します。")
        else:
            logger.info(f"言語設定: {language}")
        
        logger.info(f"文字起こし開始: {os.path.basename(file_path)}")
        
        # 文字起こしの実行
        segments, info = whisper_model.transcribe(
            file_path,
            language=language,
            beam_size=5,
            task="transcribe"
        )
        
        # 結果を文字列にまとめる
        result = []
        for segment in segments:
            if should_stop:
                logger.info("文字起こし処理が中断されました。")
                return None
            
            start_time = format_time(segment.start)
            end_time = format_time(segment.end)
            text = segment.text.strip()
            
            if text:
                result.append(f"[{start_time} -> {end_time}] {text}")
        
        logger.info(f"文字起こし完了: {os.path.basename(file_path)}")
        
        return "\n".join(result)
    
    except Exception as e:
        logger.error(f"文字起こし処理エラー: {e}")
        return None


def format_time(seconds: float) -> str:
    """秒数を[HH:MM:SS.mmm]形式に変換"""
    hours, remainder = divmod(seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{int(hours):02d}:{int(minutes):02d}:{seconds:06.3f}"


def call_llm_api(transcription: str, config: Dict[str, Any]) -> Optional[str]:
    """LLM APIを呼び出して議事録を生成"""
    try:
        llm_config = config["llm"]
        api_type = llm_config["api_type"]
        
        # デフォルトのプロンプトテンプレートを使用
        template = config["prompt_templates"]["default"]
        prompt = template.replace("{transcription}", transcription)
        
        if api_type == "openai":
            return call_openai_api(prompt, llm_config)
        elif api_type == "anthropic":
            return call_anthropic_api(prompt, llm_config)
        elif api_type == "google":
            return call_google_api(prompt, llm_config)
        else:
            logger.error(f"サポートされていないAPI種類: {api_type}")
            return None
    
    except Exception as e:
        logger.error(f"LLM API呼び出しエラー: {e}")
        return None


def call_openai_api(prompt: str, config: Dict[str, Any]) -> Optional[str]:
    """OpenAI APIを呼び出す"""
    api_key = config["api_key"]
    if not api_key:
        logger.error("OpenAI APIキーが設定されていません。")
        return None
    
    try:
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}"
        }
        
        data = {
            "model": config["model"],
            "messages": [
                {"role": "system", "content": "あなたは会議の音声文字起こしから議事録を作成する専門家です。"},
                {"role": "user", "content": prompt}
            ],
            "temperature": config["temperature"],
            "max_tokens": config["max_tokens"]
        }
        
        response = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers=headers,
            json=data
        )
        
        if response.status_code == 200:
            result = response.json()
            return result["choices"][0]["message"]["content"]
        else:
            logger.error(f"API呼び出しエラー: {response.status_code} - {response.text}")
            return None
    
    except Exception as e:
        logger.error(f"OpenAI API呼び出し例外: {e}")
        return None


def call_anthropic_api(prompt: str, config: Dict[str, Any]) -> Optional[str]:
    """Anthropic Claude APIを呼び出す"""
    api_key = config["api_key"]
    if not api_key:
        logger.error("Anthropic APIキーが設定されていません。")
        return None
    
    try:
        # 新しいClaudeのMessages API形式で呼び出し
        headers = {
            "Content-Type": "application/json",
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01"
        }
        
        data = {
            "model": config["model"],
            "messages": [
                {"role": "user", "content": prompt}
            ],
            "temperature": config["temperature"],
            "max_tokens": config["max_tokens"]
        }
        
        response = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers=headers,
            json=data
        )
        
        if response.status_code == 200:
            result = response.json()
            return result["content"][0]["text"]
        else:
            # 旧API形式での呼び出しを試みる
            headers = {
                "Content-Type": "application/json",
                "X-API-Key": api_key,
                "anthropic-version": "2023-06-01"
            }
            
            data = {
                "model": config["model"],
                "prompt": f"\n\nHuman: {prompt}\n\nAssistant:",
                "temperature": config["temperature"],
                "max_tokens_to_sample": config["max_tokens"],
            }
            
            response = requests.post(
                "https://api.anthropic.com/v1/complete",
                headers=headers,
                json=data
            )
            
            if response.status_code == 200:
                result = response.json()
                return result["completion"]
            else:
                logger.error(f"API呼び出しエラー: {response.status_code} - {response.text}")
                return None
    
    except Exception as e:
        logger.error(f"Anthropic API呼び出し例外: {e}")
        return None


def call_google_api(prompt: str, config: Dict[str, Any]) -> Optional[str]:
    """Google Gemini APIを呼び出す"""
    api_key = config.get("google_api_key", "")
    if not api_key:
        logger.error("Google APIキーが設定されていません。")
        return None
    
    try:
        # Gemini API URL
        model = config["model"]
        # モデル名に基づいてAPIパスを構築
        # API仕様に合わせてモデル名を変換
        model_id = model.replace("gemini-", "")
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_id}:generateContent?key={api_key}"
        
        headers = {
            "Content-Type": "application/json"
        }
        
        data = {
            "contents": [
                {
                    "role": "user",
                    "parts": [{"text": prompt}]
                }
            ],
            "generationConfig": {
                "temperature": config["temperature"],
                "maxOutputTokens": config["max_tokens"],
                "topP": 0.95,
                "topK": 40
            }
        }
        
        response = requests.post(url, headers=headers, json=data)
        
        if response.status_code == 200:
            result = response.json()
            # レスポンス形式に合わせて適切にパースする
            if "candidates" in result and len(result["candidates"]) > 0:
                if "content" in result["candidates"][0]:
                    if "parts" in result["candidates"][0]["content"]:
                        text_parts = []
                        for part in result["candidates"][0]["content"]["parts"]:
                            if "text" in part:
                                text_parts.append(part["text"])
                        return "".join(text_parts)
            
            logger.error(f"Google API応答の解析に失敗しました: {result}")
            return None
        else:
            logger.error(f"Google API呼び出しエラー: {response.status_code} - {response.text}")
            return None
    
    except Exception as e:
        logger.error(f"Google API呼び出し例外: {e}")
        return None


def save_output(content: str, original_file: str, config: Dict[str, Any]) -> str:
    """生成された議事録を保存"""
    output_dir = config["file_watcher"]["output_directory"]
    if not output_dir:
        output_dir = os.path.dirname(original_file)
    
    # 出力ディレクトリが存在しない場合は作成
    os.makedirs(output_dir, exist_ok=True)
    
    # 出力ファイル名を生成
    base_name = os.path.splitext(os.path.basename(original_file))[0]
    timestamp = datetime.now().strftime("%Y-%m%d-%H%M")
    output_file = os.path.join(output_dir, f"{base_name}_memo_{timestamp}.txt")
    
    # 内容を保存
    with open(output_file, "w", encoding="utf-8") as f:
        f.write(content)
    
    logger.info(f"議事録を保存しました: {output_file}")
    return output_file


def process_file_queue():
    """ファイルキューを処理"""
    global should_stop, config
    
    logger.info("ファイル処理スレッドを開始しました。")
    config = load_config()
    
    while not should_stop:
        try:
            # キューからファイルを取得（タイムアウト付き）
            try:
                file_path = file_queue.get(timeout=1)
            except queue.Empty:
                continue
            
            # 処理済みかどうかの再チェック（キューに入った後に他のプロセスで処理された可能性）
            if is_file_processed(file_path):
                logger.info(f"ファイルは既に処理済みです（キュー内再チェック）: {file_path}")
                file_queue.task_done()
                continue
            
            # ファイル処理
            logger.info(f"処理開始: {file_path}")
            
            # 1. 文字起こし
            transcription = transcribe_file(file_path, config)
            if not transcription or should_stop:
                logger.warning(f"文字起こしに失敗または中断されました: {file_path}")
                file_queue.task_done()
                continue
            
            # 文字起こし結果を保存（オプション）
            base_dir = os.path.dirname(file_path)
            base_name = os.path.splitext(os.path.basename(file_path))[0]
            timestamp = datetime.now().strftime("%Y-%m%d-%H%M")
            transcript_file = os.path.join(base_dir, f"{base_name}_transcript_{timestamp}.txt")
            with open(transcript_file, "w", encoding="utf-8") as f:
                f.write(transcription)
            logger.info(f"文字起こし結果を保存しました: {transcript_file}")
            
            # 2. LLM API呼び出し
            memo = call_llm_api(transcription, config)
            if not memo or should_stop:
                logger.warning(f"議事録生成に失敗または中断されました: {file_path}")
                file_queue.task_done()
                continue
            
            # 3. 結果を保存
            output_file = save_output(memo, file_path, config)
            logger.info(f"ファイル処理が完了しました: {file_path} -> {output_file}")
            
            # 4. 処理済みとしてマーク
            mark_file_as_processed(file_path, output_file)
            
            # キューのタスク完了を通知
            file_queue.task_done()
        
        except Exception as e:
            logger.exception(f"ファイル処理中に例外が発生しました: {e}")
            try:
                file_queue.task_done()
            except:
                pass
    
    logger.info("ファイル処理スレッドを終了しました。")


def start_file_watcher(config: Dict[str, Any]) -> Optional[Observer]:
    """ファイル監視を開始"""
    input_dir = config["file_watcher"]["input_directory"]
    
    if not input_dir:
        logger.error("入力ディレクトリが設定されていません。")
        return None
    
    if not os.path.exists(input_dir):
        try:
            os.makedirs(input_dir, exist_ok=True)
            logger.info(f"入力ディレクトリを作成しました: {input_dir}")
        except Exception as e:
            logger.error(f"入力ディレクトリの作成に失敗しました: {e}")
            return None
    
    try:
        event_handler = MediaFileHandler(config)
        observer = Observer()
        observer.schedule(event_handler, input_dir, recursive=False)
        observer.start()
        logger.info(f"ディレクトリ監視を開始しました: {input_dir}")
        return observer
    
    except Exception as e:
        logger.error(f"ファイル監視の開始に失敗しました: {e}")
        return None


def check_existing_files(config: Dict[str, Any]):
    """監視ディレクトリ内の既存ファイルを確認しキューに追加"""
    input_dir = config["file_watcher"]["input_directory"]
    if not input_dir or not os.path.exists(input_dir):
        return
    
    extensions = config["file_watcher"]["supported_extensions"]
    count = 0
    processed_count = 0
    
    for file in os.listdir(input_dir):
        file_path = os.path.join(input_dir, file)
        if os.path.isfile(file_path):
            ext = os.path.splitext(file)[-1].lower()
            if ext in extensions:
                # 処理済みかどうかチェック
                if is_file_processed(file_path):
                    processed_count += 1
                    continue
                    
                file_queue.put(file_path)
                count += 1
    
    if count > 0:
        logger.info(f"ディレクトリ内の未処理メディアファイル {count}個 をキューに追加しました。")
    if processed_count > 0:
        logger.info(f"ディレクトリ内の処理済みメディアファイル {processed_count}個 をスキップしました。")


def validate_config(config: Dict[str, Any]) -> bool:
    """設定の妥当性を検証"""
    # 必須キーの確認
    required_keys = [
        "transcription", "llm", "file_watcher", "prompt_templates"
    ]
    
    for key in required_keys:
        if key not in config:
            logger.error(f"設定ファイルに必須キー '{key}' がありません。")
            return False
    
    # ディレクトリの設定を確認
    if not config["file_watcher"]["input_directory"]:
        logger.warning("入力ディレクトリが設定されていません。設定GUIから設定してください。")
    
    if not config["file_watcher"]["output_directory"]:
        logger.warning("出力ディレクトリが設定されていません。入力ディレクトリと同じになります。")
    
    # LLM API設定の確認
    api_type = config["llm"]["api_type"]
    if api_type == "openai" and not config["llm"]["api_key"]:
        logger.warning("OpenAI APIキーが設定されていません。設定GUIから設定してください。")
    elif api_type == "anthropic" and not config["llm"]["api_key"]:
        logger.warning("Anthropic APIキーが設定されていません。設定GUIから設定してください。")
    elif api_type == "google" and not config["llm"].get("google_api_key"):
        logger.warning("Google APIキーが設定されていません。設定GUIから設定してください。")
    
    # 入出力ディレクトリのチェック（異なるディレクトリを推奨）
    input_dir = config["file_watcher"]["input_directory"]
    output_dir = config["file_watcher"]["output_directory"]
    if input_dir and output_dir and input_dir == output_dir:
        logger.warning("入力ディレクトリと出力ディレクトリが同じです。別のディレクトリを使用することを推奨します。")
    
    return True


def start_service():
    """サービスの開始"""
    global processing_thread, observer, should_stop, config
    
    # 設定の読み込みと検証
    config = load_config()
    if not validate_config(config):
        logger.error("設定の検証に失敗しました。")
        return False
    
    # FFmpegのチェック
    if not check_ffmpeg():
        logger.error("FFmpegがインストールされていないか、PATHに設定されていません。")
        logger.error("FFmpegをインストールして、PATHに追加してください。")
        return False
    
    # 処理済みファイルリストのクリーンアップ
    clean_old_processed_files()
    
    # ファイル処理スレッドの開始
    should_stop = False
    processing_thread = threading.Thread(target=process_file_queue, daemon=True)
    processing_thread.start()
    
    # ファイル監視の開始
    observer = start_file_watcher(config)
    if not observer:
        stop_service()
        return False
    
    # 既存ファイルのチェック
    check_existing_files(config)
    
    logger.info("KoeMemoサービスが開始されました。")
    return True


def stop_service():
    """サービスの停止"""
    global processing_thread, observer, should_stop
    
    # 停止フラグの設定
    should_stop = True
    
    # ファイル監視の停止
    if observer:
        observer.stop()
        observer.join()
        observer = None
    
    # 処理スレッドの待機
    if processing_thread and processing_thread.is_alive():
        processing_thread.join(timeout=5)
        processing_thread = None
    
    logger.info("KoeMemoサービスが停止されました。")


def check_directories_interactively():
    """対話的にディレクトリを設定"""
    global config
    config = load_config()
    
    # 入力ディレクトリの確認
    input_dir = config["file_watcher"]["input_directory"]
    if not input_dir:
        print("\n入力ディレクトリが設定されていません。")
        while True:
            path = input("監視する入力ディレクトリのパスを入力してください: ").strip()
            if not path:
                continue
                
            # パスを正規化
            path = os.path.normpath(os.path.expanduser(path))
            
            if not os.path.exists(path):
                try:
                    os.makedirs(path, exist_ok=True)
                    print(f"ディレクトリを作成しました: {path}")
                except Exception as e:
                    print(f"ディレクトリの作成に失敗しました: {e}")
                    continue
            
            config["file_watcher"]["input_directory"] = path
            break
    
    # 出力ディレクトリの確認
    output_dir = config["file_watcher"]["output_directory"]
    if not output_dir:
        print("\n出力ディレクトリが設定されていません。")
        print("1. 入力ディレクトリと同じにする")
        print("2. 別のディレクトリを指定する")
        
        choice = input("選択してください (1/2): ").strip()
        if choice == "2":
            while True:
                path = input("出力ディレクトリのパスを入力してください: ").strip()
                if not path:
                    continue
                    
                # パスを正規化
                path = os.path.normpath(os.path.expanduser(path))
                
                if not os.path.exists(path):
                    try:
                        os.makedirs(path, exist_ok=True)
                        print(f"ディレクトリを作成しました: {path}")
                    except Exception as e:
                        print(f"ディレクトリの作成に失敗しました: {e}")
                        continue
                
                config["file_watcher"]["output_directory"] = path
                break
        else:
            # 入力ディレクトリと同じにする
            config["file_watcher"]["output_directory"] = config["file_watcher"]["input_directory"]
            print("注意: 入力と出力が同じディレクトリの場合、既存ファイルのチェックが重要です。")
    
    # APIキーの確認
    api_type = config["llm"]["api_type"]
    if api_type == "openai" and not config["llm"]["api_key"]:
        print("\nOpenAI APIキーが設定されていません。")
        api_key = input("APIキーを入力してください（入力しない場合は最小限機能で実行）: ").strip()
        if api_key:
            config["llm"]["api_key"] = api_key
    elif api_type == "anthropic" and not config["llm"]["api_key"]:
        print("\nAnthropic APIキーが設定されていません。")
        api_key = input("APIキーを入力してください（入力しない場合は最小限機能で実行）: ").strip()
        if api_key:
            config["llm"]["api_key"] = api_key
    elif api_type == "google" and not config["llm"].get("google_api_key"):
        print("\nGoogle APIキーが設定されていません。")
        api_key = input("APIキーを入力してください（入力しない場合は最小限機能で実行）: ").strip()
        if api_key:
            config["llm"]["google_api_key"] = api_key
    
    # 設定の保存
    save_config(config)
    print("\n設定を保存しました。")


def main():
    """メインエントリーポイント"""
    print("KoeMemo - 音声・動画ファイルから自動的に議事録を生成するツール")
    print("======================================================")
    
    try:
        # 最初の設定確認
        check_directories_interactively()
        
        print("\nKoeMemoサービスを開始しています...")
        if start_service():
            print("サービスが正常に開始されました。Ctrl+Cで終了できます。")
            
            # メインスレッドを維持
            try:
                while True:
                    time.sleep(1)
            except KeyboardInterrupt:
                print("\nKoeMemoサービスを停止しています...")
                stop_service()
                print("サービスが停止しました。")
        else:
            print("サービスの開始に失敗しました。ログを確認してください。")
    
    except Exception as e:
        logger.exception(f"予期しない例外が発生しました: {e}")
        print(f"エラーが発生しました: {e}")
        stop_service()
        return 1
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
