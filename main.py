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
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

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

try:
    import tkinter as tk
    from tkinter import ttk, filedialog, messagebox
except ImportError:
    print("エラー: tkinterモジュールが利用できません。")
    print("Pythonにtkinterがインストールされていることを確認してください。")
    sys.exit(1)

# ロガーの設定
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',  # name（ロガー名）を削除
    datefmt='%Y-%m-%d %H:%M:%S',  # 秒までの表示に変更（ミリ秒を削除）
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("koememo.log", encoding="utf-8")
    ]
)
logger = logging.getLogger("app")

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


# GUIクラス
class KoeMemoGUI:
    """設定用GUIクラス"""
    
    def __init__(self, root: tk.Tk):
        """グラフィックユーザーインタフェースの初期化"""
        self.root = root
        self.root.title("KoeMemo - 設定")
        
        # ウィンドウを画面中央に配置
        self.center_window()
        
        # アイコンの設定（存在する場合）
        icon_path = Path(__file__).parent / "icon.ico"
        if icon_path.exists():
            self.root.iconbitmap(str(icon_path))
        
        # 設定の読み込み
        self.config = self.load_config()
        
        # サービス状態
        self.service_running = False
        self.service_thread = None
        
        # UI構築
        self.build_ui()

    def center_window(self):
        """ウィンドウを画面中央に配置"""
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        
        window_width = 900
        window_height = 700
        
        x = (screen_width - window_width) // 2
        y = (screen_height - window_height) // 2
        
        self.root.geometry(f"{window_width}x{window_height}+{x}+{y}")

    def load_config(self) -> Dict[str, Any]:
        """設定ファイルの読み込み"""
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                config = json.load(f)
                
                # LLMモデルリストが存在しない場合はデフォルト値を設定
                if "llm_models" not in config:
                    config["llm_models"] = {
                        "openai": [
                            "gpt-4o",
                            "gpt-4o-mini",
                            "gpt-4-turbo",
                            "gpt-4",
                            "gpt-3.5-turbo",
                            "gpt-3.5-turbo-16k"
                        ],
                        "anthropic": [
                            "claude-3-opus-20240229",
                            "claude-3-sonnet-20240229",
                            "claude-3-haiku-20240307"
                        ],
                        "google": [
                            "gemini-1.5-pro",
                            "gemini-1.5-flash",
                            "gemini-pro"
                        ]
                    }
                    # 更新した設定を保存
                    with open(CONFIG_PATH, "w", encoding="utf-8") as f_save:
                        json.dump(config, f_save, ensure_ascii=False, indent=4)
                    
                return config
        except (FileNotFoundError, json.JSONDecodeError) as e:
            logger.error(f"設定ファイルの読み込みエラー: {e}")
            messagebox.showerror("エラー", f"設定ファイルの読み込みに失敗しました: {e}")
            return {}

    def save_config(self):
        """設定ファイルの保存"""
        try:
            with open(CONFIG_PATH, "w", encoding="utf-8") as f:
                json.dump(self.config, f, ensure_ascii=False, indent=4)
            logger.info("設定を保存しました。")
        except Exception as e:
            logger.error(f"設定ファイルの保存エラー: {e}")
            messagebox.showerror("エラー", f"設定ファイルの保存に失敗しました: {e}")

    def build_ui(self):
        """ユーザーインタフェースの構築"""
        # タブコントロール
        notebook = ttk.Notebook(self.root)
        notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # 基本設定タブ
        basic_frame = ttk.Frame(notebook, padding=10)
        notebook.add(basic_frame, text="基本設定")
        
        # モデル設定タブ
        model_frame = ttk.Frame(notebook, padding=10)
        notebook.add(model_frame, text="モデル設定")
        
        # LLM設定タブ
        llm_frame = ttk.Frame(notebook, padding=10)
        notebook.add(llm_frame, text="LLM設定")
        
        # テンプレートタブ
        template_frame = ttk.Frame(notebook, padding=10)
        notebook.add(template_frame, text="テンプレート")
        
        # モデル管理タブ
        models_frame = ttk.Frame(notebook, padding=10)
        notebook.add(models_frame, text="モデル管理")
        
        # 基本設定タブの内容
        self.build_basic_settings(basic_frame)
        
        # モデル設定タブの内容
        self.build_model_settings(model_frame)
        
        # LLM設定タブの内容
        self.build_llm_settings(llm_frame)
        
        # テンプレートタブの内容
        self.build_template_settings(template_frame)
        
        # モデル管理タブの内容
        self.build_models_management(models_frame)
        
        # ステータスと操作ボタン
        status_frame = ttk.Frame(self.root, padding=10)
        status_frame.pack(fill=tk.X, side=tk.BOTTOM)
        
        # ステータスラベル
        self.status_var = tk.StringVar(value="サービスは停止しています")
        status_label = ttk.Label(status_frame, textvariable=self.status_var)
        status_label.pack(side=tk.LEFT, padx=5)
        
        # ボタン
        self.start_stop_button = ttk.Button(status_frame, text="サービス開始", command=self.toggle_service)
        self.start_stop_button.pack(side=tk.RIGHT, padx=5)
        
        ttk.Button(status_frame, text="設定保存", command=self.save_config_and_reload).pack(side=tk.RIGHT, padx=5)


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
    
    # GUI実行中の場合は処理済みファイルリストを更新
    try:
        # tkが初期化されていて、GUIのルートウィンドウが存在する場合のみ
        if 'Tk' in sys.modules and hasattr(sys.modules['tkinter'], '_default_root') and sys.modules['tkinter']._default_root:
            root = sys.modules['tkinter']._default_root
            # GUIインスタンスがアクセス可能か確認
            for widget in root.winfo_children():
                if hasattr(widget, 'master') and hasattr(widget.master, 'update_processed_files'):
                    # 遅延実行で処理済みファイルリストを更新
                    root.after(1000, widget.master.update_processed_files)
                    break
    except Exception as e:
        logger.debug(f"GUIの処理済みファイルリスト更新中にエラーが発生しました（無視可能）: {e}")


def load_config() -> Dict[str, Any]:
    """設定ファイルの読み込み"""
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            config_data = json.load(f)
            
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


def clean_old_processed_files(max_entries: int = 1000):
    """古い処理済みファイル情報をクリーンアップ"""
    global config
    
    processed_files = config.get("processed_files", {})
    if not processed_files:
        return
    
    # エントリ数が上限を超えている場合にクリーンアップ
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
        
        base_filename = os.path.basename(file_path)
        # モデル情報を取得
        model_size = config["transcription"]["model_size"]
        compute_type = config["transcription"]["compute_type"]
        device = "cuda" if is_cuda_available() else "cpu"
        
        logger.info(f"文字起こし開始: {base_filename} (モデル: {model_size}, デバイス: {device}, 計算タイプ: {compute_type})")
        
        # 文字起こしの実行
        segments, info = whisper_model.transcribe(
            file_path,
            language=language,
            beam_size=5,
            task="transcribe"
        )
        
        # 結果を文字列にまとめる - ジェネレータをそのまま処理
        result = []
        segment_count = 0
        last_progress_time = time.time()
        estimated_segments = 0  # 推定セグメント数（音声の長さから概算）
        
        # segmentsはジェネレータなのでリストに変換せずに処理
        for segment in segments:
            segment_count += 1
            
            # 10セグメントごと、または5秒ごとに進捗をログに表示
            current_time = time.time()
            if segment_count % 10 == 0 or segment_count == 1 or (current_time - last_progress_time) >= 5:
                last_progress_time = current_time
                text_preview = segment.text.strip()
                # テキストをログに表示（長い場合は省略）
                if len(text_preview) > 30:
                    text_preview = text_preview[:27] + "..."
                logger.info(f"文字起こし進捗: セグメント {segment_count} - \"{text_preview}\"")
                
            if should_stop:
                logger.info("文字起こし処理が中断されました。")
                return None
            
            start_time = format_time(segment.start)
            end_time = format_time(segment.end)
            text = segment.text.strip()
            
            if text:
                result.append(f"[{start_time} -> {end_time}] {text}")
        
        logger.info(f"✅ 文字起こし完了: {os.path.basename(file_path)} - 合計 {segment_count} セグメント処理")
        
        return "\n".join(result)
    
    except FileNotFoundError:
        logger.error(f"ファイルが見つかりません: {file_path}")
        return None
    except PermissionError:
        logger.error(f"ファイルにアクセスする権限がありません: {file_path}")
        return None
    except RuntimeError as e:
        logger.error(f"Whisperモデル実行エラー: {e}")
        return None
    except Exception as e:
        logger.error(f"文字起こし処理エラー: {e}")
        return None


def format_time(seconds: float) -> str:
    """秒数を[HH:MM:SS]形式に変換（小数点以下を省略）"""
    hours, remainder = divmod(seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{int(hours):02d}:{int(minutes):02d}:{int(seconds):02d}"


def split_transcription(transcription: str, chunk_size: int = 5000) -> List[Dict[str, Any]]:
    """文字起こしをチャンクに分割
    
    Args:
        transcription: 文字起こしテキスト
        chunk_size: 各チャンクの最大文字数（デフォルト: 5000文字）
        
    Returns:
        分割されたチャンクのリスト。各チャンクは辞書形式で、
        index, start_time, end_time, contentキーを持つ
    """
    lines = transcription.split("\n")
    chunks = []
    current_chunk = []
    current_size = 0
    chunk_index = 1
    
    # 時間情報を抽出するための正規表現
    time_pattern = r"\[(\d{2}:\d{2}:\d{2})"
    
    start_time = None
    end_time = None
    
    for line in lines:
        line_size = len(line) + 1  # 改行文字を考慮
        
        # 最初の行から開始時間を抽出
        if not start_time and line:
            start_match = re.search(time_pattern, line)
            if start_match:
                start_time = start_match.group(1)
        
        # チャンクサイズを超える場合、新しいチャンクを開始
        if current_size + line_size > chunk_size and current_chunk:
            # 最後の行から終了時間を抽出
            if current_chunk[-1]:
                end_match = re.search(time_pattern, current_chunk[-1])
                if end_match:
                    end_time = end_match.group(1)
            
            # チャンク情報を追加
            chunks.append({
                "index": chunk_index,
                "start_time": start_time or "00:00:00.000",
                "end_time": end_time or "unknown",
                "content": "\n".join(current_chunk)
            })
            
            # 新しいチャンクの準備
            current_chunk = []
            current_size = 0
            chunk_index += 1
            # 次のチャンクの開始時間は、現在の終了時間から始まる
            start_time = end_time
            end_time = None
        
        current_chunk.append(line)
        current_size += line_size
    
    # 最後のチャンクを処理
    if current_chunk:
        if current_chunk[-1]:
            end_match = re.search(time_pattern, current_chunk[-1])
            if end_match:
                end_time = end_match.group(1)
        
        chunks.append({
            "index": chunk_index,
            "start_time": start_time or "00:00:00.000",
            "end_time": end_time or "unknown",
            "content": "\n".join(current_chunk)
        })
    
    # チャンク情報をログに出力
    for chunk in chunks:
        start_time = chunk['start_time'] if chunk['start_time'] != "unknown" else "00:00:00"
        end_time = chunk['end_time'] if chunk['end_time'] != "unknown" else "最後まで"
        logger.info(f"チャンク {chunk['index']}: {start_time} -> {end_time}, サイズ: {len(chunk['content'])}文字")
    
    return chunks


def is_long_transcription(transcription: str, config: Dict[str, Any]) -> bool:
    """文字起こしが長いかどうかを判定する
    
    Args:
        transcription: 判定する文字起こしテキスト
        config: アプリケーション設定
        
    Returns:
        True: 長い文字起こしと判定された場合
        False: 通常の長さと判定された場合
    """
    # 文字数で判定
    char_count = len(transcription)
    processing_config = config.get("processing", {})
    
    # chunking が有効かどうか確認
    chunking_enabled = processing_config.get("enable_chunking", True)
    if not chunking_enabled:
        logger.info("分割処理が無効に設定されています。標準処理を使用します。")
        return False
    
    # 選択されたLLMモデルの情報を取得
    llm_config = config.get("llm", {})
    model_name = llm_config.get("model", "").lower()
    api_type = llm_config.get("api_type", "openai").lower()
    
    # モデルに基づいて閾値を調整
    chunk_size = processing_config.get("chunk_size", 12000)
    threshold_multiplier = 3  # デフォルトの閾値乗数
    
    # モデル特性に基づく調整
    if api_type == "openai":
        if "gpt-4o" in model_name or "gpt-4-turbo" in model_name:
            # GPT-4oやGPT-4-turboはより大きなコンテキストを処理可能
            threshold_multiplier = 3
        elif "gpt-3.5" in model_name:
            # GPT-3.5は小さめのコンテキスト
            threshold_multiplier = 2.5
    elif api_type == "anthropic":
        if "opus" in model_name:
            threshold_multiplier = 3.5
        elif "sonnet" in model_name:
            threshold_multiplier = 3
        else:  # haiku等
            threshold_multiplier = 2.5
    elif api_type == "google":
        if "1.5-pro" in model_name:
            threshold_multiplier = 3.5
        else:
            threshold_multiplier = 3
    
    # チャンクサイズと乗数に基づいて閾値を計算
    threshold = int(chunk_size * threshold_multiplier)
    is_long = char_count > threshold
    
    if is_long:
        logger.info(f"長い文字起こしを検出: 約{char_count}文字（閾値: {threshold}文字、モデル: {model_name}）")
    
    return is_long


def call_llm_api(transcription: str, config: Dict[str, Any]) -> Optional[str]:
    """LLM APIを呼び出して議事録を生成"""
    try:
        # 長い文字起こしかどうかをチェック
        if is_long_transcription(transcription, config):
            logger.info("長い文字起こしを検出したため、分割処理を適用します")
            return process_chunked_transcription(transcription, config)
            
        # 通常の処理（短い文字起こし）
        llm_config = config["llm"]
        api_type = llm_config["api_type"]
        
        # 選択されたテンプレートを使用（設定されていない場合はデフォルト）
        template_name = llm_config.get("selected_template", "default")
        if not template_name or template_name not in config["prompt_templates"]:
            template_name = "default"
            logger.warning(f"指定されたテンプレート '{template_name}' が見つかりません。デフォルトを使用します。")
        
        template = config["prompt_templates"][template_name]
        prompt = template.replace("{transcription}", transcription)
        
        logger.info(f"LLM API ({api_type}) 呼び出し開始 - テンプレート: {template_name}")
        
        result = None
        if api_type == "openai":
            result = call_openai_api(prompt, llm_config)
        elif api_type == "anthropic":
            result = call_anthropic_api(prompt, llm_config)
        elif api_type == "google":
            result = call_google_api(prompt, llm_config)
        else:
            logger.error(f"サポートされていないAPI種類: {api_type}")
            return None
            
        if result:
            logger.info(f"✅ LLM API ({api_type}) 呼び出し完了: 約{len(result)}文字の応答を受信")
        else:
            logger.error(f"❌ LLM API ({api_type}) 呼び出し失敗: 応答なし")
            
        return result
    
    except Exception as e:
        logger.error(f"❌ LLM API呼び出しエラー: {e}")
        return None


def call_llm_api_for_chunk(chunk: Dict[str, Any], config: Dict[str, Any]) -> Optional[str]:
    """チャンク用のLLM API呼び出し
    
    Args:
        chunk: 処理するチャンク情報（index, start_time, end_time, content）
        config: アプリケーション設定
        
    Returns:
        要約結果テキスト、または失敗時はNone
    """
    try:
        llm_config = config["llm"]
        api_type = llm_config["api_type"]
        
        # テンプレート取得
        template_name = llm_config.get("selected_template", "default")
        if not template_name or template_name not in config["prompt_templates"]:
            template_name = "default"
            logger.warning(f"指定されたテンプレート '{template_name}' が見つかりません。デフォルトを使用します。")
        
        template = config["prompt_templates"][template_name]
        
        # チャンク情報を組み込んだプロンプトを作成（タイムスタンプ部分の表示を保証するための処理）
        start_time = chunk['start_time'] if chunk['start_time'] != "unknown" else "00:00:00"
        end_time = chunk['end_time'] if chunk['end_time'] != "unknown" else "最後まで"
        part_info = f"会議記録 第{chunk['index']}部（{start_time}～{end_time}）"
        
        # テンプレートにチャンク情報を追加
        modified_template = f"{template}\n\n注: これは{part_info}の要約です。"
        prompt = modified_template.replace("{transcription}", chunk["content"])
        
        logger.info(f"LLM API ({api_type}) 呼び出し開始 - チャンク {chunk['index']}")
        
        # 通常のLLM API呼び出し処理を実行
        result = None
        if api_type == "openai":
            result = call_openai_api(prompt, llm_config)
        elif api_type == "anthropic":
            result = call_anthropic_api(prompt, llm_config)
        elif api_type == "google":
            result = call_google_api(prompt, llm_config)
        else:
            logger.error(f"サポートされていないAPI種類: {api_type}")
            return None
        
        if result:
            logger.info(f"✅ チャンク {chunk['index']} の要約完了: 約{len(result)}文字")
            # 要約にパート情報を追加
            result = f"## {part_info}\n\n{result}"
        else:
            logger.error(f"❌ チャンク {chunk['index']} の要約に失敗しました")
        
        return result
    
    except Exception as e:
        logger.error(f"❌ チャンク {chunk['index']} のLLM API呼び出しエラー: {e}")
        return None


def process_chunked_transcription(transcription: str, config: Dict[str, Any]) -> Optional[str]:
    """長い文字起こしの分割処理
    
    Args:
        transcription: 文字起こしテキスト全体
        config: アプリケーション設定
        
    Returns:
        処理結果の要約テキスト、または失敗時はNone
    """
    # 設定から分割サイズを取得
    processing_config = config.get("processing", {})
    chunk_size = processing_config.get("chunk_size", 5000)
    
    # 文字起こしを分割
    chunks = split_transcription(transcription, chunk_size)
    logger.info(f"文字起こしを {len(chunks)} チャンクに分割しました")
    
    # 各チャンクを処理
    chunk_summaries = []
    for chunk in chunks:
        summary = call_llm_api_for_chunk(chunk, config)
        if summary:
            chunk_summaries.append(summary)
        else:
            logger.warning(f"⚠️ チャンク {chunk['index']} の要約に失敗しました")
    
    # すべてのチャンクが処理失敗した場合
    if not chunk_summaries:
        logger.error("❌ すべてのチャンクの処理に失敗しました")
        return None
    
    # 要約を結合
    combined_summary = "\n\n".join(chunk_summaries)
    
    # 二段階要約が有効な場合は全体要約を生成
    if processing_config.get("two_stage_summary", False) and len(chunks) > 1:
        logger.info("全体要約を生成します...")
        
        # 各チャンクの要約をまとめた全体要約を生成
        overall_summary = create_overall_summary(chunk_summaries, config)
        if overall_summary:
            combined_summary = f"# 会議全体の要約\n\n{overall_summary}\n\n# チャンク別詳細\n\n{combined_summary}"
            logger.info("全体要約の生成が完了しました")
        else:
            logger.warning("全体要約の生成に失敗しました")
    
    return combined_summary

def create_overall_summary(chunk_summaries: List[str], config: Dict[str, Any]) -> Optional[str]:
    """各チャンクの要約から全体要約を生成する
    
    Args:
        chunk_summaries: 各チャンクの要約テキストのリスト
        config: アプリケーション設定
        
    Returns:
        全体要約テキスト、または失敗時はNone
    """
    try:
        llm_config = config["llm"]
        api_type = llm_config["api_type"]
        
        # すべてのチャンク要約を組み合わせたテキスト
        combined_text = "\n\n".join(chunk_summaries)
        
        # 全体要約用のプロンプト
        prompt = f"""
以下は会議の各パートの要約です。これらの要約を統合して、会議全体の簡潔な要約を生成してください。

重要な点：
- 全体の流れを把握できるようにする
- 重要な意思決定や結論を強調する
- 矛盾する情報があれば調整して一貫性のある要約にする
- 重複内容は一度だけ記載する

以下の会議パート要約から全体要約を作成してください：

{combined_text}
"""
        
        logger.info(f"全体要約のLLM API ({api_type}) 呼び出し開始")
        
        # LLM API呼び出し
        result = None
        if api_type == "openai":
            result = call_openai_api(prompt, llm_config)
        elif api_type == "anthropic":
            result = call_anthropic_api(prompt, llm_config)
        elif api_type == "google":
            result = call_google_api(prompt, llm_config)
        else:
            logger.error(f"サポートされていないAPI種類: {api_type}")
            return None
        
        if result:
            logger.info(f"✅ 全体要約の生成完了: 約{len(result)}文字の応答を受信")
            return result
        else:
            logger.error("❌ 全体要約の生成に失敗しました")
            return None
    
    except Exception as e:
        logger.error(f"❌ 全体要約の生成エラー: {e}")
        return None


def call_openai_api(prompt: str, config: Dict[str, Any]) -> Optional[str]:
    """OpenAI APIを呼び出す"""
    api_key = config["api_key"]
    if not api_key:
        logger.error("❌ OpenAI APIキーが設定されていません。")
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
            logger.error(f"❌ API呼び出しエラー: {response.status_code} - {response.text}")
            return None
    
    except Exception as e:
        logger.error(f"❌ OpenAI API呼び出し例外: {e}")
        return None


def call_anthropic_api(prompt: str, config: Dict[str, Any]) -> Optional[str]:
    """Anthropic Claude APIを呼び出す"""
    api_key = config["api_key"]
    if not api_key:
        logger.error("❌ Anthropic APIキーが設定されていません。")
        return None
    
    try:
        # Claude Messages API形式で呼び出し
        headers = {
            "Content-Type": "application/json",
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01"  # APIバージョン
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
            logger.error(f"❌ API呼び出しエラー: {response.status_code} - {response.text}")
            return None
    
    except Exception as e:
        logger.error(f"❌ Anthropic API呼び出し例外: {e}")
        return None


def call_google_api(prompt: str, config: Dict[str, Any]) -> Optional[str]:
    """Google Gemini APIを呼び出す"""
    api_key = config.get("google_api_key", "")
    if not api_key:
        logger.error("❌ Google APIキーが設定されていません。")
        return None
    
    try:
        # Gemini API URL
        model = config["model"]
        # モデル名に基づいてAPIパスを構築
        # API仕様に合わせてモデル名をそのまま使用
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
        
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
            logger.error(f"❌ Google API呼び出しエラー: {response.status_code} - {response.text}")
            return None
    
    except Exception as e:
        logger.error(f"❌ Google API呼び出し例外: {e}")
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
            base_filename = os.path.basename(file_path)
            logger.info(f"🔄 ===== 処理開始: {base_filename} =====")
            logger.info(f"📋 処理ステップ [1/4]: 文字起こし準備")
            
            # 1. 文字起こし
            logger.info(f"🔄 処理ステップ [2/4]: 文字起こし実行中...")
            transcription = transcribe_file(file_path, config)
            if not transcription or should_stop:
                logger.warning(f"❌ 文字起こしに失敗または中断されました: {file_path}")
                file_queue.task_done()
                continue
            
            # 文字起こし結果を保存
            base_name = os.path.splitext(os.path.basename(file_path))[0]
            timestamp = datetime.now().strftime("%Y-%m%d-%H%M")
            
            # 文字起こしディレクトリに保存
            transcript_dir = config["file_watcher"]["transcript_directory"]
            # ディレクトリの存在チェックは validate_config で行われているので、ここでは省略
            
            transcript_file = os.path.join(transcript_dir, f"{base_name}_transcript_{timestamp}.txt")
            with open(transcript_file, "w", encoding="utf-8") as f:
                f.write(transcription)
            logger.info(f"✅ 文字起こし結果を保存しました: {transcript_file}")
            
            # 2. LLM API呼び出し
            logger.info(f"🔄 処理ステップ [3/4]: LLM APIで議事録生成中...")
            memo = call_llm_api(transcription, config)
            
            if not memo or should_stop:
                logger.warning(f"❌ 議事録生成に失敗または中断されました: {file_path}")
                file_queue.task_done()
                continue
            
            # 3. 結果を保存
            logger.info(f"🔄 処理ステップ [4/4]: 議事録保存中...")
            output_file = save_output(memo, file_path, config)
            
            logger.info(f"✅✅ 処理完了: {base_filename}")
            logger.info(f"📄 出力ファイル: {output_file}")
            logger.info(f"===== 処理終了: {base_filename} =====")
            
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
        logger.error("入力ディレクトリが設定されていません。設定GUIから設定してください。")
        return False
    
    if not config["file_watcher"]["output_directory"]:
        logger.error("出力ディレクトリが設定されていません。設定GUIから設定してください。")
        return False
    
    # 文字起こしディレクトリの確認
    transcript_dir = config["file_watcher"].get("transcript_directory", "")
    if not transcript_dir:
        logger.error("文字起こしディレクトリが設定されていません。設定GUIから設定してください。")
        return False
        
    # 各ディレクトリの存在チェックと作成処理
    input_dir = config["file_watcher"]["input_directory"]
    output_dir = config["file_watcher"]["output_directory"]
    
    for dir_name, dir_path in [("入力", input_dir), ("文字起こし", transcript_dir), ("出力", output_dir)]:
        if not os.path.exists(dir_path):
            try:
                os.makedirs(dir_path, exist_ok=True)
                logger.info(f"{dir_name}ディレクトリを作成しました: {dir_path}")
            except Exception as e:
                logger.error(f"{dir_name}ディレクトリの作成に失敗しました: {e}")
                return False
    
    # LLM API設定の確認
    api_type = config["llm"]["api_type"]
    if api_type == "openai" and not config["llm"]["api_key"]:
        logger.warning("OpenAI APIキーが設定されていません。設定GUIから設定してください。")
    elif api_type == "anthropic" and not config["llm"]["api_key"]:
        logger.warning("Anthropic APIキーが設定されていません。設定GUIから設定してください。")
    elif api_type == "google" and not config["llm"].get("google_api_key"):
        logger.warning("Google APIキーが設定されていません。設定GUIから設定してください。")
    
    # 入出力ディレクトリのチェック（異なるディレクトリを推奨）
    if input_dir == output_dir:
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
    
    logger.info("🚀 KoeMemoサービスが開始されました。")
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
    
    logger.info("🛑 KoeMemoサービスが停止されました。")


def main():
    """メインエントリーポイント"""
    print("KoeMemo - 音声・動画ファイルから自動的に議事録を生成するツール")
    print("======================================================")
    
    try:
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
