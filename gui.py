#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
KoeMemo - 設定GUI
シンプルな設定画面を提供するGUIモジュール
"""

import os
import sys
import json
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
import threading
import subprocess
import logging
import time
import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional, List

# 設定ファイルのパス
CONFIG_PATH = Path(__file__).parent / "config.json"
LOG_FILE_PATH = Path(__file__).parent / "koememo.log"

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
logger = logging.getLogger("gui")

# メインサービスのインポート
try:
    import main as koememo_service
except ImportError:
    logger.error("main.pyをインポートできませんでした。")
    sys.exit(1)


class KoeMemoGUI:
    """KoeMemoの設定GUI"""

    def __init__(self, root: tk.Tk):
        """GUIの初期化"""
        self.root = root
        self.root.title("KoeMemo")
        # 初期サイズを大きく設定（画面中央配置時に上書きされる）
        self.root.geometry("1200x700")
        
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
        
        # ログ更新用変数
        self.log_update_running = False
        self.log_update_thread = None
        
        # UI構築
        self.build_ui()
    
    def center_window(self):
        """ウィンドウを画面中央に配置"""
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        
        window_width = 1200  # 横幅を900から1200に拡大
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
            logger.info("✅ 設定を保存しました。")
        except Exception as e:
            logger.error(f"❌ 設定ファイルの保存エラー: {e}")
            messagebox.showerror("エラー", f"設定ファイルの保存に失敗しました: {e}")

    def build_ui(self):
        """UIの構築"""
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
        
        # プロンプトタブ
        template_frame = ttk.Frame(notebook, padding=10)
        notebook.add(template_frame, text="プロンプト")
        
        # モデル管理タブ
        models_frame = ttk.Frame(notebook, padding=10)
        notebook.add(models_frame, text="モデル管理")
        
        # ログビューワータブ
        log_frame = ttk.Frame(notebook, padding=10)
        notebook.add(log_frame, text="ログビューワー")
        
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
        
        # ログビューワータブの内容
        self.build_log_viewer(log_frame)
        
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

    def build_basic_settings(self, parent: ttk.Frame):
        """基本設定タブの構築"""
        # 説明フレーム（新規追加）
        info_frame = ttk.LabelFrame(parent, text="KoeMemo へようこそ！", padding=10)
        info_frame.pack(fill=tk.X, pady=5)
        
        info_text = (
            "このアプリケーションは、音声・動画ファイルから自動的に文字起こしを行い、AIによる議事録を生成します。\n\n"
            "【使用方法】\n"
            "1. 各ディレクトリを設定してください（すべて必須です）\n"
            "   - 入力ディレクトリ：処理したい音声・動画ファイルを置くフォルダ\n"
            "   - 文字起こしディレクトリ：文字起こし結果を保存するフォルダ\n"
            "   - 出力ディレクトリ：生成された議事録を保存するフォルダ\n\n"
            "2. 対応する拡張子のファイルが自動的に処理されます\n"
            "   - 音声：mp3, wav, m4a, flac\n"
            "   - 動画：mp4, avi, mov, wmv\n\n"
            "3. 設定が完了したら「サービス開始」ボタンをクリックし、入力フォルダにファイルを追加するだけで自動処理が始まります。\n\n"
            "※ 議事録生成には「LLM設定」タブでAPIキーの設定が必要です。設定がない場合は文字起こしのみ行われます。"
        )
        
        info_label = ttk.Label(info_frame, text=info_text, wraplength=700, justify="left")
        info_label.pack(fill=tk.X, padx=5, pady=5)
        
        # 入力ディレクトリ
        input_frame = ttk.Frame(parent)
        input_frame.pack(fill=tk.X, pady=5)
        
        ttk.Label(input_frame, text="入力ディレクトリ:").grid(row=0, column=0, sticky=tk.W, padx=5, pady=5)
        
        self.input_dir_var = tk.StringVar(value=self.config.get("file_watcher", {}).get("input_directory", ""))
        input_entry = ttk.Entry(input_frame, textvariable=self.input_dir_var, width=50)
        input_entry.grid(row=0, column=1, sticky=tk.EW, padx=5, pady=5)
        
        ttk.Button(input_frame, text="参照...", command=self.browse_input_dir).grid(row=0, column=2, padx=5, pady=5)
        
        # 文字起こしディレクトリ
        transcript_frame = ttk.Frame(parent)
        transcript_frame.pack(fill=tk.X, pady=5)
        
        ttk.Label(transcript_frame, text="文字起こしディレクトリ:").grid(row=0, column=0, sticky=tk.W, padx=5, pady=5)
        
        self.transcript_dir_var = tk.StringVar(value=self.config.get("file_watcher", {}).get("transcript_directory", ""))
        transcript_entry = ttk.Entry(transcript_frame, textvariable=self.transcript_dir_var, width=50)
        transcript_entry.grid(row=0, column=1, sticky=tk.EW, padx=5, pady=5)
        
        ttk.Button(transcript_frame, text="参照...", command=self.browse_transcript_dir).grid(row=0, column=2, padx=5, pady=5)
        
        # 出力ディレクトリ
        output_frame = ttk.Frame(parent)
        output_frame.pack(fill=tk.X, pady=5)
        
        ttk.Label(output_frame, text="出力ディレクトリ:").grid(row=0, column=0, sticky=tk.W, padx=5, pady=5)
        
        self.output_dir_var = tk.StringVar(value=self.config.get("file_watcher", {}).get("output_directory", ""))
        output_entry = ttk.Entry(output_frame, textvariable=self.output_dir_var, width=50)
        output_entry.grid(row=0, column=1, sticky=tk.EW, padx=5, pady=5)
        
        ttk.Button(output_frame, text="参照...", command=self.browse_output_dir).grid(row=0, column=2, padx=5, pady=5)
        
        # 対応拡張子
        extensions_frame = ttk.Frame(parent)
        extensions_frame.pack(fill=tk.X, pady=5)
        
        ttk.Label(extensions_frame, text="対応拡張子:").grid(row=0, column=0, sticky=tk.W, padx=5, pady=5)
        
        extensions = self.config.get("file_watcher", {}).get("supported_extensions", [])
        self.extensions_var = tk.StringVar(value=", ".join(extensions).replace(".", ""))
        extensions_entry = ttk.Entry(extensions_frame, textvariable=self.extensions_var, width=50)
        extensions_entry.grid(row=0, column=1, sticky=tk.EW, padx=5, pady=5)
        ttk.Label(extensions_frame, text="カンマ区切りで入力").grid(row=0, column=2, padx=5, pady=5)

    def build_model_settings(self, parent: ttk.Frame):
        """モデル設定タブの構築"""
        # モデルサイズ
        model_size_frame = ttk.Frame(parent)
        model_size_frame.pack(fill=tk.X, pady=5)
        
        ttk.Label(model_size_frame, text="モデルサイズ:").grid(row=0, column=0, sticky=tk.W, padx=5, pady=5)
        
        sizes = ["tiny", "base", "small", "medium", "large"]
        self.model_size_var = tk.StringVar(value=self.config.get("transcription", {}).get("model_size", "medium"))
        model_size_combo = ttk.Combobox(model_size_frame, textvariable=self.model_size_var, values=sizes, state="readonly", width=15)
        model_size_combo.grid(row=0, column=1, sticky=tk.W, padx=5, pady=5)
        
        # 言語設定
        language_frame = ttk.Frame(parent)
        language_frame.pack(fill=tk.X, pady=5)
        
        ttk.Label(language_frame, text="言語:").grid(row=0, column=0, sticky=tk.W, padx=5, pady=5)
        
        languages = [("自動検出", "auto"), ("日本語", "ja"), ("英語", "en")]
        self.language_var = tk.StringVar()
        
        # 設定の言語コードからラベルに変換
        language_code = self.config.get("transcription", {}).get("language", "ja")
        for label, code in languages:
            if code == language_code:
                self.language_var.set(label)
                break
        else:
            self.language_var.set("自動検出")
        
        language_combo = ttk.Combobox(language_frame, textvariable=self.language_var, values=[lang[0] for lang in languages], state="readonly", width=15)
        language_combo.grid(row=0, column=1, sticky=tk.W, padx=5, pady=5)
        
        # 計算タイプ
        compute_frame = ttk.Frame(parent)
        compute_frame.pack(fill=tk.X, pady=5)
        
        ttk.Label(compute_frame, text="計算タイプ:").grid(row=0, column=0, sticky=tk.W, padx=5, pady=5)
        
        compute_types = ["int8", "float16", "float32"]
        self.compute_type_var = tk.StringVar(value=self.config.get("transcription", {}).get("compute_type", "int8"))
        compute_type_combo = ttk.Combobox(compute_frame, textvariable=self.compute_type_var, values=compute_types, state="readonly", width=15)
        compute_type_combo.grid(row=0, column=1, sticky=tk.W, padx=5, pady=5)
        
        # 注意書き
        note_frame = ttk.LabelFrame(parent, text="注意", padding=10)
        note_frame.pack(fill=tk.X, pady=10)
        
        note_text = (
            "• モデルサイズが大きいほど精度が高くなりますが、処理時間とメモリ使用量も増加します。\n"
            "• CPUのみの環境では計算タイプは自動的に「int8」が使用されます。\n"
            "• 言語を指定すると認識精度が向上する場合があります。\n"
            "• 初回実行時には選択したモデルがダウンロードされるため、インターネット接続が必要です。"
        )
        ttk.Label(note_frame, text=note_text, wraplength=700, justify="left").pack(fill=tk.X)

    def build_llm_settings(self, parent: ttk.Frame):
        """LLM設定タブの構築"""
        # API種類
        api_type_frame = ttk.Frame(parent)
        api_type_frame.pack(fill=tk.X, pady=5)
        
        ttk.Label(api_type_frame, text="API種類:").grid(row=0, column=0, sticky=tk.W, padx=5, pady=5)
        
        api_types = list(self.config.get("llm_models", {}).keys())
        if not api_types:
            api_types = ["openai", "anthropic", "google"]
            
        self.api_type_var = tk.StringVar(value=self.config.get("llm", {}).get("api_type", "openai"))
        api_type_combo = ttk.Combobox(api_type_frame, textvariable=self.api_type_var, values=api_types, state="readonly", width=15)
        api_type_combo.grid(row=0, column=1, sticky=tk.W, padx=5, pady=5)
        api_type_combo.bind("<<ComboboxSelected>>", self.update_model_options)
        
        # APIキー
        self.api_key_frame = ttk.Frame(parent)
        self.api_key_frame.pack(fill=tk.X, pady=5)
        
        ttk.Label(self.api_key_frame, text="APIキー:").grid(row=0, column=0, sticky=tk.W, padx=5, pady=5)
        
        self.api_key_var = tk.StringVar(value=self.config.get("llm", {}).get("api_key", ""))
        api_key_entry = ttk.Entry(self.api_key_frame, textvariable=self.api_key_var, width=50, show="*")
        api_key_entry.grid(row=0, column=1, sticky=tk.EW, padx=5, pady=5)
        
        # Google APIキー（Google選択時のみ表示）
        self.google_api_key_frame = ttk.Frame(parent)
        self.google_api_key_var = tk.StringVar(value=self.config.get("llm", {}).get("google_api_key", ""))
        
        ttk.Label(self.google_api_key_frame, text="Google APIキー:").grid(row=0, column=0, sticky=tk.W, padx=5, pady=5)
        google_api_key_entry = ttk.Entry(self.google_api_key_frame, textvariable=self.google_api_key_var, width=50, show="*")
        google_api_key_entry.grid(row=0, column=1, sticky=tk.EW, padx=5, pady=5)
        
        # APIタイプに応じてフレームを表示/非表示
        if self.api_type_var.get() == "google":
            self.google_api_key_frame.pack(fill=tk.X, pady=5)
        else:
            self.google_api_key_frame.pack_forget()
        
        # モデル
        self.model_frame = ttk.Frame(parent)
        self.model_frame.pack(fill=tk.X, pady=5)
        
        ttk.Label(self.model_frame, text="モデル:").grid(row=0, column=0, sticky=tk.W, padx=5, pady=5)
        
        self.model_var = tk.StringVar(value=self.config.get("llm", {}).get("model", "gpt-4"))
        self.model_combo = ttk.Combobox(self.model_frame, textvariable=self.model_var, state="readonly", width=30)
        self.model_combo.grid(row=0, column=1, sticky=tk.W, padx=5, pady=5)
        
        # モデルオプションを更新
        self.update_model_options()
        
        # Temperature
        temp_frame = ttk.Frame(parent)
        temp_frame.pack(fill=tk.X, pady=5)
        
        ttk.Label(temp_frame, text="Temperature:").grid(row=0, column=0, sticky=tk.W, padx=5, pady=5)
        
        self.temp_var = tk.DoubleVar(value=self.config.get("llm", {}).get("temperature", 0.3))
        temp_scale = ttk.Scale(temp_frame, from_=0.0, to=1.0, variable=self.temp_var, orient=tk.HORIZONTAL, length=200)
        temp_scale.grid(row=0, column=1, sticky=tk.W, padx=5, pady=5)
        
        temp_label = ttk.Label(temp_frame, textvariable=self.temp_var, width=5)
        temp_label.grid(row=0, column=2, padx=5, pady=5)
        
        # Max Tokens
        tokens_frame = ttk.Frame(parent)
        tokens_frame.pack(fill=tk.X, pady=5)
        
        ttk.Label(tokens_frame, text="最大トークン数:").grid(row=0, column=0, sticky=tk.W, padx=5, pady=5)
        
        self.max_tokens_var = tk.IntVar(value=self.config.get("llm", {}).get("max_tokens", 1500))
        tokens_spinbox = ttk.Spinbox(tokens_frame, from_=100, to=4000, textvariable=self.max_tokens_var, width=10)
        tokens_spinbox.grid(row=0, column=1, sticky=tk.W, padx=5, pady=5)
        
        # 注意書き
        note_frame = ttk.LabelFrame(parent, text="注意", padding=10)
        note_frame.pack(fill=tk.X, pady=10)
        
        note_text = (
            "• APIキーは各サービスから取得してください。\n"
            "• OpenAI APIを使用する場合: https://platform.openai.com/ から取得したAPIキーを「APIキー」欄に入力\n"
            "• Anthropic Claude APIを使用する場合: https://console.anthropic.com/ から取得したAPIキーを「APIキー」欄に入力\n"
            "• Google Gemini APIを使用する場合: https://aistudio.google.com/ または Google Cloud Consoleから取得したAPIキーを「Google APIキー」欄に入力\n"
            "• APIの使用には料金が発生する場合があります。各サービスの料金体系を確認してください。\n"
            "• Temperatureが低いほど決定的な出力になり、高いほど多様な出力になります。\n"
            "• 最大トークン数は生成される議事録の長さに影響します。"
        )
        ttk.Label(note_frame, text=note_text, wraplength=700, justify="left").pack(fill=tk.X)

    def update_model_options(self, event=None):
        """APIタイプに基づいてモデルオプションを更新"""
        api_type = self.api_type_var.get()
        
        # APIタイプに応じてキー入力フィールドを表示/非表示
        if api_type == "google":
            self.google_api_key_frame.pack(fill=tk.X, pady=5, after=self.api_key_frame)
        else:
            self.google_api_key_frame.pack_forget()
        
        # モデルリストを設定ファイルから取得
        models = self.config.get("llm_models", {}).get(api_type, [])
        
        # デフォルトモデルリスト（設定がない場合のフォールバック）
        if not models:
            if api_type == "openai":
                models = ["gpt-3.5-turbo", "gpt-4", "gpt-4o", "gpt-4o-mini"]
            elif api_type == "anthropic":
                models = ["claude-3-opus-20240229", "claude-3-sonnet-20240229"]
            elif api_type == "google":
                models = ["gemini-pro", "gemini-1.5-pro"]
        
        self.model_combo["values"] = models
        
        # 現在のモデルが新しいリストにない場合はデフォルト値に設定
        if self.model_var.get() not in models and models:
            self.model_var.set(models[0])

    def build_models_management(self, parent: ttk.Frame):
        """モデル管理タブの構築"""
        # 説明ラベル
        ttk.Label(parent, text="LLMプロバイダとモデルの管理", font=("", 12, "bold")).pack(pady=10)
        ttk.Label(parent, text="各プロバイダーごとに使用可能なモデルを編集できます。").pack(pady=5)
        
        # プロバイダー選択
        provider_frame = ttk.Frame(parent)
        provider_frame.pack(fill=tk.X, pady=10)
        
        ttk.Label(provider_frame, text="プロバイダー:").pack(side=tk.LEFT, padx=5)
        
        llm_providers = list(self.config.get("llm_models", {}).keys())
        if not llm_providers:
            llm_providers = ["openai", "anthropic", "google"]
            
        self.provider_var = tk.StringVar(value=llm_providers[0] if llm_providers else "")
        provider_combo = ttk.Combobox(provider_frame, textvariable=self.provider_var, values=llm_providers, state="readonly", width=15)
        provider_combo.pack(side=tk.LEFT, padx=5)
        provider_combo.bind("<<ComboboxSelected>>", self.load_provider_models)
        
        # 新規プロバイダー追加
        self.new_provider_var = tk.StringVar()
        new_provider_entry = ttk.Entry(provider_frame, textvariable=self.new_provider_var, width=15)
        new_provider_entry.pack(side=tk.LEFT, padx=5)
        
        ttk.Button(provider_frame, text="プロバイダー追加", command=self.add_provider).pack(side=tk.LEFT, padx=5)
        ttk.Button(provider_frame, text="プロバイダー削除", command=self.delete_provider).pack(side=tk.LEFT, padx=5)
        
        # モデルリスト編集用フレーム
        models_edit_frame = ttk.LabelFrame(parent, text="モデルリスト", padding=10)
        models_edit_frame.pack(fill=tk.BOTH, expand=True, pady=10)
        
        # モデルリストエディタ
        self.models_text = tk.Text(models_edit_frame, wrap=tk.WORD, height=10)
        self.models_text.pack(fill=tk.BOTH, expand=True, side=tk.LEFT)
        
        models_scrollbar = ttk.Scrollbar(models_edit_frame, command=self.models_text.yview)
        models_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.models_text.config(yscrollcommand=models_scrollbar.set)
        
        # 説明
        ttk.Label(parent, text="各モデルを1行に1つずつ入力してください。").pack(pady=5)
        
        # 保存ボタン
        save_frame = ttk.Frame(parent)
        save_frame.pack(fill=tk.X, pady=10)
        
        ttk.Button(save_frame, text="モデルリスト保存", command=self.save_models).pack(side=tk.RIGHT, padx=5)
        
        # 初期表示
        if self.provider_var.get():
            self.load_provider_models()

    def load_provider_models(self, event=None):
        """選択されたプロバイダーのモデルリストを読み込む"""
        provider = self.provider_var.get()
        if not provider:
            return
            
        # モデルリストを取得
        models = self.config.get("llm_models", {}).get(provider, [])
        
        # テキストエリアに表示
        self.models_text.delete(1.0, tk.END)
        self.models_text.insert(tk.END, "\n".join(models))

    def save_models(self):
        """モデルリストを保存"""
        provider = self.provider_var.get()
        if not provider:
            messagebox.showwarning("警告", "プロバイダーが選択されていません。")
            return
            
        # テキストエリアからモデルリストを取得
        models_text = self.models_text.get(1.0, tk.END).strip()
        models = [model.strip() for model in models_text.split("\n") if model.strip()]
        
        # 設定に保存
        if "llm_models" not in self.config:
            self.config["llm_models"] = {}
            
        self.config["llm_models"][provider] = models
        self.save_config()
        
        # モデル選択コンボボックスの更新（現在のAPIタイプと一致する場合）
        if self.api_type_var.get() == provider:
            self.update_model_options()
            
        messagebox.showinfo("情報", f"プロバイダー「{provider}」のモデルリストを保存しました。")

    def add_provider(self):
        """新しいプロバイダーを追加"""
        new_provider = self.new_provider_var.get().strip().lower()
        
        if not new_provider:
            messagebox.showwarning("警告", "プロバイダー名を入力してください。")
            return
            
        # すでに存在する場合は警告
        if new_provider in self.config.get("llm_models", {}):
            messagebox.showwarning("警告", f"プロバイダー「{new_provider}」は既に存在します。")
            return
            
        # 新しいプロバイダーを追加
        if "llm_models" not in self.config:
            self.config["llm_models"] = {}
            
        self.config["llm_models"][new_provider] = []
        self.save_config()
        
        # コンボボックスを更新
        providers = list(self.config["llm_models"].keys())
        provider_combo = self.provider_var.master.children["!combobox"]
        provider_combo["values"] = providers
        self.provider_var.set(new_provider)
        
        # APIタイプのコンボボックスも更新
        api_type_combo = self.api_type_var.master.master.children["!combobox"]
        api_type_combo["values"] = providers
        
        # モデルリストをクリア
        self.models_text.delete(1.0, tk.END)
        
        messagebox.showinfo("情報", f"新しいプロバイダー「{new_provider}」を追加しました。")
        self.new_provider_var.set("")

    def delete_provider(self):
        """プロバイダーを削除"""
        provider = self.provider_var.get()
        
        if not provider:
            messagebox.showwarning("警告", "プロバイダーが選択されていません。")
            return
            
        # 最低1つは残す
        if len(self.config.get("llm_models", {})) <= 1:
            messagebox.showwarning("警告", "少なくとも1つのプロバイダーが必要です。削除できません。")
            return
            
        # 確認ダイアログ
        if not messagebox.askyesno("確認", f"プロバイダー「{provider}」を削除してもよろしいですか？\n関連するすべてのモデルリストも削除されます。"):
            return
            
        # 削除
        del self.config["llm_models"][provider]
        self.save_config()
        
        # コンボボックスを更新
        providers = list(self.config["llm_models"].keys())
        provider_combo = self.provider_var.master.children["!combobox"]
        provider_combo["values"] = providers
        self.provider_var.set(providers[0] if providers else "")
        
        # APIタイプのコンボボックスも更新
        api_type_combo = self.api_type_var.master.master.children["!combobox"]
        api_type_combo["values"] = providers
        
        # 現在のAPIタイプが削除されたものと同じ場合は変更
        if self.api_type_var.get() == provider:
            self.api_type_var.set(providers[0] if providers else "")
            self.update_model_options()
            
        # モデルリストを更新
        self.load_provider_models()
        
        messagebox.showinfo("情報", f"プロバイダー「{provider}」を削除しました。")

    def build_template_settings(self, parent: ttk.Frame):
        """プロンプト設定タブの構築"""
        # プロンプト選択
        template_selector_frame = ttk.Frame(parent)
        template_selector_frame.pack(fill=tk.X, pady=5)
        
        ttk.Label(template_selector_frame, text="プロンプト:").pack(side=tk.LEFT, padx=5, pady=5)
        
        templates = list(self.config.get("prompt_templates", {}).keys())
        
        # 現在選択されているプロンプトを取得（設定されていなければ最初のプロンプト）
        selected_template = self.config.get("llm", {}).get("selected_template", "")
        if not selected_template or selected_template not in templates:
            selected_template = templates[0] if templates else ""
            
        self.template_var = tk.StringVar(value=selected_template)
        self.template_combo = ttk.Combobox(template_selector_frame, textvariable=self.template_var, values=templates, state="readonly", width=20)
        self.template_combo.pack(side=tk.LEFT, padx=5, pady=5)
        self.template_combo.bind("<<ComboboxSelected>>", self.load_template)
        
        # 新規プロンプト名
        self.new_template_var = tk.StringVar()
        new_template_entry = ttk.Entry(template_selector_frame, textvariable=self.new_template_var, width=20)
        new_template_entry.pack(side=tk.LEFT, padx=5, pady=5)
        
        ttk.Button(template_selector_frame, text="新規作成", command=self.create_template).pack(side=tk.LEFT, padx=5, pady=5)
        ttk.Button(template_selector_frame, text="削除", command=self.delete_template).pack(side=tk.LEFT, padx=5, pady=5)
        
        # プロンプト編集
        template_edit_frame = ttk.LabelFrame(parent, text="プロンプト編集", padding=10)
        template_edit_frame.pack(fill=tk.BOTH, expand=True, pady=5)
        
        # プロンプトテキスト
        self.template_text = tk.Text(template_edit_frame, wrap=tk.WORD, height=15)
        self.template_text.pack(fill=tk.BOTH, expand=True, side=tk.LEFT)
        
        template_scrollbar = ttk.Scrollbar(template_edit_frame, command=self.template_text.yview)
        template_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.template_text.config(yscrollcommand=template_scrollbar.set)
        
        # 保存ボタン
        ttk.Button(parent, text="プロンプト保存", command=self.save_template).pack(anchor=tk.E, padx=5, pady=5)
        
        # プレースホルダーの説明
        placeholder_frame = ttk.LabelFrame(parent, text="使用可能なプレースホルダー", padding=10)
        placeholder_frame.pack(fill=tk.X, pady=5)
        
        placeholder_text = (
            "• {transcription} - 文字起こしの全文\n"
            "• {filename} - 元のファイル名\n"
            "• {date} - 処理日付\n"
            "• {time} - 処理時刻"
        )
        ttk.Label(placeholder_frame, text=placeholder_text, wraplength=700, justify="left").pack(fill=tk.X)
        
        # 初期プロンプトの読み込み
        if templates:
            self.load_template()

    def load_template(self, event=None):
        """選択されたプロンプトを読み込む"""
        template_name = self.template_var.get()
        if not template_name:
            return
        
        template_content = self.config.get("prompt_templates", {}).get(template_name, "")
        
        self.template_text.delete(1.0, tk.END)
        self.template_text.insert(tk.END, template_content)
        
        # 選択されたプロンプトを設定に反映
        if "llm" not in self.config:
            self.config["llm"] = {}
        self.config["llm"]["selected_template"] = template_name
        
        # 設定変更をディスクに保存（頻繁に保存しすぎるのを避けるためeventがある場合のみ）
        if event:
            self.save_config()

    def save_template(self):
        """現在のプロンプトを保存"""
        template_name = self.template_var.get()
        if not template_name:
            messagebox.showwarning("警告", "プロンプトが選択されていません。")
            return
        
        template_content = self.template_text.get(1.0, tk.END).strip()
        
        if not template_content:
            messagebox.showwarning("警告", "プロンプト内容が空です。")
            return
        
        if "prompt_templates" not in self.config:
            self.config["prompt_templates"] = {}
        
        self.config["prompt_templates"][template_name] = template_content
        
        # 選択されたプロンプトを設定に反映
        if "llm" not in self.config:
            self.config["llm"] = {}
        self.config["llm"]["selected_template"] = template_name
        
        self.save_config()
        
        messagebox.showinfo("情報", f"✅ プロンプト「{template_name}」を保存しました。")

    def create_template(self):
        """新しいプロンプトを作成"""
        new_name = self.new_template_var.get().strip()
        
        if not new_name:
            messagebox.showwarning("警告", "プロンプト名を入力してください。")
            return
        
        if "prompt_templates" not in self.config:
            self.config["prompt_templates"] = {}
        
        if new_name in self.config["prompt_templates"]:
            messagebox.showwarning("警告", f"プロンプト「{new_name}」は既に存在します。")
            return
        
        # デフォルトのプロンプト内容を設定
        self.config["prompt_templates"][new_name] = "以下は会議の文字起こしです。これを元に、議事録を作成してください。\n\n文字起こし内容：\n{transcription}"
        
        # プロンプトリストを更新
        templates = list(self.config["prompt_templates"].keys())
        self.template_combo["values"] = templates
        self.template_var.set(new_name)
        
        # 選択されたプロンプトを設定に反映
        if "llm" not in self.config:
            self.config["llm"] = {}
        self.config["llm"]["selected_template"] = new_name
        
        # プロンプトを読み込む
        self.load_template()
        
        # 設定を保存
        self.save_config()
        
        messagebox.showinfo("情報", f"新しいプロンプト「{new_name}」を作成しました。")
        self.new_template_var.set("")

    def delete_template(self):
        """プロンプトを削除"""
        template_name = self.template_var.get()
        
        if not template_name:
            messagebox.showwarning("警告", "プロンプトが選択されていません。")
            return
        
        if "prompt_templates" not in self.config or template_name not in self.config["prompt_templates"]:
            messagebox.showwarning("警告", f"プロンプト「{template_name}」が見つかりません。")
            return
        
        # 確認ダイアログ
        if not messagebox.askyesno("確認", f"プロンプト「{template_name}」を削除してもよろしいですか？"):
            return
        
        # 少なくとも1つのプロンプトを残す
        if len(self.config["prompt_templates"]) <= 1:
            messagebox.showwarning("警告", "少なくとも1つのプロンプトが必要です。削除できません。")
            return
        
        # プロンプトを削除
        del self.config["prompt_templates"][template_name]
        
        # プロンプトリストを更新
        templates = list(self.config["prompt_templates"].keys())
        self.template_combo["values"] = templates
        new_selected_template = templates[0] if templates else ""
        self.template_var.set(new_selected_template)
        
        # 選択されたプロンプトを設定に反映
        if "llm" in self.config and "selected_template" in self.config["llm"]:
            if self.config["llm"]["selected_template"] == template_name:
                self.config["llm"]["selected_template"] = new_selected_template
        
        # プロンプトを読み込む
        self.load_template()
        
        # 設定を保存
        self.save_config()
        
        messagebox.showinfo("情報", f"プロンプト「{template_name}」を削除しました。")

    def browse_input_dir(self):
        """入力ディレクトリを選択"""
        directory = filedialog.askdirectory(initialdir=self.input_dir_var.get() or os.path.expanduser("~"))
        if directory:
            self.input_dir_var.set(directory)

    def browse_output_dir(self):
        """出力ディレクトリを選択"""
        directory = filedialog.askdirectory(initialdir=self.output_dir_var.get() or os.path.expanduser("~"))
        if directory:
            self.output_dir_var.set(directory)

    def browse_transcript_dir(self):
        """文字起こしディレクトリを選択"""
        directory = filedialog.askdirectory(initialdir=self.transcript_dir_var.get() or os.path.expanduser("~"))
        if directory:
            self.transcript_dir_var.set(directory)

    def update_config_from_ui(self):
        """UI入力から設定を更新"""
        # ファイル監視設定
        if "file_watcher" not in self.config:
            self.config["file_watcher"] = {}
        
        self.config["file_watcher"]["input_directory"] = self.input_dir_var.get()
        self.config["file_watcher"]["output_directory"] = self.output_dir_var.get()
        self.config["file_watcher"]["transcript_directory"] = self.transcript_dir_var.get()
        
        # 拡張子の処理
        extensions = [f".{ext.strip()}" for ext in self.extensions_var.get().split(",") if ext.strip()]
        self.config["file_watcher"]["supported_extensions"] = extensions
        
        # 文字起こし設定
        if "transcription" not in self.config:
            self.config["transcription"] = {}
        
        self.config["transcription"]["model_size"] = self.model_size_var.get()
        
        # 言語設定（表示名からコードに変換）
        language_display = self.language_var.get()
        language_mapping = {"自動検出": "auto", "日本語": "ja", "英語": "en"}
        self.config["transcription"]["language"] = language_mapping.get(language_display, "auto")
        
        self.config["transcription"]["compute_type"] = self.compute_type_var.get()
        
        # LLM設定
        if "llm" not in self.config:
            self.config["llm"] = {}
        
        self.config["llm"]["api_type"] = self.api_type_var.get()
        self.config["llm"]["api_key"] = self.api_key_var.get()
        
        # Google APIキーを設定
        self.config["llm"]["google_api_key"] = self.google_api_key_var.get()
        
        self.config["llm"]["model"] = self.model_var.get()
        self.config["llm"]["temperature"] = self.temp_var.get()
        self.config["llm"]["max_tokens"] = self.max_tokens_var.get()
        
        # 選択中のテンプレート名を保存
        self.config["llm"]["selected_template"] = self.template_var.get()
        
        # テンプレート設定は保存済み（save_template内で処理）

    def save_config_and_reload(self):
        """設定を保存して再読み込み"""
        self.update_config_from_ui()
        self.save_config()
        messagebox.showinfo("情報", "設定を保存しました。")
        
        # サービスが実行中の場合は再起動
        if self.service_running:
            self.restart_service()

    def toggle_service(self):
        """サービスの開始/停止の切り替え"""
        if self.service_running:
            self.stop_service()
        else:
            # サービス開始前に必須ディレクトリが設定されているか確認
            if not self.input_dir_var.get():
                messagebox.showerror("エラー", "入力ディレクトリが設定されていません。\n設定してから再試行してください。")
                return
                
            if not self.transcript_dir_var.get():
                messagebox.showerror("エラー", "文字起こしディレクトリが設定されていません。\n設定してから再試行してください。")
                return
                
            if not self.output_dir_var.get():
                messagebox.showerror("エラー", "出力ディレクトリが設定されていません。\n設定してから再試行してください。")
                return
            
            # 設定を保存してからサービス開始
            self.save_config()
            self.start_service()

    def start_service(self):
        """サービスを開始"""
        # 設定を保存
        self.update_config_from_ui()
        self.save_config()
        
        # 入力ディレクトリの確認
        input_dir = self.input_dir_var.get()
        if not input_dir:
            messagebox.showwarning("警告", "入力ディレクトリが設定されていません。")
            return
        
        try:
            # サービスのスレッドを開始
            self.service_thread = threading.Thread(
                target=self.run_service,
                daemon=True
            )
            self.service_thread.start()
            
            # UI更新
            self.service_running = True
            self.status_var.set("サービスは実行中です")
            self.start_stop_button.config(text="サービス停止")
            
            messagebox.showinfo("情報", "🚀 KoeMemoサービスを開始しました。")
        
        except Exception as e:
            logger.error(f"サービス開始エラー: {e}")
            messagebox.showerror("エラー", f"サービスの開始に失敗しました: {e}")

    def run_service(self):
        """サービス実行スレッド"""
        try:
            # サービスを起動
            koememo_service.start_service()
            
            # サービスが終了するまで待機
            while self.service_running:
                time.sleep(1)
        
        except Exception as e:
            logger.exception(f"サービス実行中にエラーが発生しました: {e}")
            # GUIスレッドで実行するためにafterを使用
            self.root.after(0, lambda: messagebox.showerror("エラー", f"サービス実行エラー: {e}"))
            self.root.after(0, self.stop_service)

    def stop_service(self):
        """サービスを停止"""
        if not self.service_running:
            return
        
        try:
            # サービスを停止
            koememo_service.stop_service()
            
            # UI更新
            self.service_running = False
            self.status_var.set("サービスは停止しています")
            self.start_stop_button.config(text="サービス開始")
            
            messagebox.showinfo("情報", "🛑 KoeMemoサービスを停止しました。")
        
        except Exception as e:
            logger.error(f"サービス停止エラー: {e}")
            messagebox.showerror("エラー", f"サービスの停止に失敗しました: {e}")

    def restart_service(self):
        """サービスを再起動"""
        if self.service_running:
            self.stop_service()
            # 少し待機してから再開
            self.root.after(1000, self.start_service)
        else:
            self.start_service()

    def on_closing(self):
        """ウィンドウクローズ時の処理"""
        # ログ更新スレッドの停止
        self.log_update_running = False
        
        if self.service_running:
            if messagebox.askyesno("確認", "サービスが実行中です。停止してアプリケーションを終了しますか？"):
                self.stop_service()
                self.root.destroy()
        else:
            self.root.destroy()

    def build_log_viewer(self, parent: ttk.Frame):
        """ログビューワータブの構築"""
        # 操作フレーム
        control_frame = ttk.Frame(parent)
        control_frame.pack(fill=tk.X, pady=5)
        
        # 表示順序選択のラジオボタン
        order_frame = ttk.LabelFrame(control_frame, text="表示順序")
        order_frame.pack(side=tk.LEFT, padx=5, pady=5)
        
        self.order_var = tk.StringVar(value="desc")  # デフォルトは降順（最新が上）
        ttk.Radiobutton(order_frame, text="降順（最新が上）", variable=self.order_var, 
                      value="desc", command=self.refresh_logs).pack(anchor=tk.W, padx=5)
        ttk.Radiobutton(order_frame, text="昇順（最新が下）", variable=self.order_var, 
                      value="asc", command=self.refresh_logs).pack(anchor=tk.W, padx=5)
        
        # 検索入力
        ttk.Label(control_frame, text="検索:").pack(side=tk.LEFT, padx=5)
        self.search_var = tk.StringVar()
        search_entry = ttk.Entry(control_frame, textvariable=self.search_var, width=30)
        search_entry.pack(side=tk.LEFT, padx=5)
        
        # 検索ボタン
        ttk.Button(control_frame, text="検索", command=self.search_logs).pack(side=tk.LEFT, padx=5)
        
        # ボタン用のフレーム
        button_frame = ttk.Frame(control_frame)
        button_frame.pack(side=tk.RIGHT, padx=5)
        
        # リフレッシュボタン
        update_button = ttk.Button(button_frame, text="ログを更新", command=self.refresh_logs, width=12)
        update_button.pack(side=tk.LEFT, padx=5, pady=5)
        
        # クリアボタン
        clear_button = ttk.Button(button_frame, text="ログをクリア", command=self.clear_logs, width=12)
        clear_button.pack(side=tk.LEFT, padx=5, pady=5)
        
        # ログテキストエリア（サイズを大きく）
        self.log_text = scrolledtext.ScrolledText(parent, width=120, height=30, wrap=tk.WORD)
        self.log_text.pack(fill=tk.BOTH, expand=True, pady=5)
        
        # 初期ログの読み込み
        self.refresh_logs()
        
        # ログ更新スレッドの開始
        self.start_log_updates()
    
    def start_log_updates(self):
        """ログ更新スレッドを開始"""
        if not self.log_update_running:
            self.log_update_running = True
            self.log_update_thread = threading.Thread(
                target=self.update_logs_periodically,
                daemon=True
            )
            self.log_update_thread.start()
    
    def update_logs_periodically(self):
        """ログを定期的に更新するスレッド"""
        while self.log_update_running:
            # GUIスレッドでログを更新（遅延実行）
            self.root.after(100, self.refresh_logs)  # 遅延を追加（0→100ms）
            # 2秒待機（大幅に待機時間を増やす）
            time.sleep(2)
    
    # 以前のログ内容を保持する変数
    _previous_log_content = ""
    _previous_order = None  # 前回の表示順序を記憶
    
    def refresh_logs(self):
        """ログファイルの内容を更新（内容が変わった場合のみ）"""
        try:
            if LOG_FILE_PATH.exists():
                # 現在のスクロール位置を記録
                current_first_line = self.log_text.index("@0,0")
                
                # ファイル内容を読み込み
                with open(LOG_FILE_PATH, "r", encoding="utf-8") as f:
                    log_content = f.read()
                
                # 表示順序を取得
                current_order = self.order_var.get()
                
                # 内容と表示順が前回と同じならスキップ（スクロール位置が変わるのを防ぐ）
                if (log_content == self.__class__._previous_log_content and 
                    current_order == self.__class__._previous_order):
                    return
                    
                # 表示順序を記憶
                self.__class__._previous_order = current_order
                
                # 表示するコンテンツを準備（昇順/降順の選択に応じて）
                lines = log_content.splitlines()
                
                # 選択された表示順に応じて処理
                if self.order_var.get() == "desc":  # 降順（最新が上）
                    lines.reverse()  # 行を逆順にする
                    
                display_content = "\n".join(lines)
                    
                # 新しい内容を保存
                self.__class__._previous_log_content = log_content  # 元のコンテンツを保存（比較用）
                
                # テキストを置換
                self.log_text.delete(1.0, tk.END)
                self.log_text.insert(tk.END, display_content)
                
                # 検索キーワードがあれば強調表示
                if self.search_var.get():
                    self.search_logs()
                    
                # 元の位置に戻す
                try:
                    self.log_text.see(current_first_line)
                except:
                    # 行が存在しない場合は何もしない
                    pass
                
            else:
                self.log_text.delete(1.0, tk.END)
                self.log_text.insert(tk.END, "ログファイルが見つかりません。")
        except Exception as e:
            logger.error(f"ログ更新エラー: {e}")
            self.log_text.delete(1.0, tk.END)
            self.log_text.insert(tk.END, f"ログの読み込みに失敗しました: {e}")
    
    def clear_logs(self):
        """ログをクリアする（バックアップも作成）"""
        try:
            # 確認ダイアログを表示
            if messagebox.askyesno("確認", "ログファイルをクリアしますか？\nバックアップは自動的に作成されます。"):
                # バックアップを作成
                if LOG_FILE_PATH.exists():
                    # 現在の日時を含むバックアップファイル名
                    backup_timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    backup_path = LOG_FILE_PATH.with_name(f"koememo_{backup_timestamp}.log.bak")
                    shutil.copy2(LOG_FILE_PATH, backup_path)
                    
                    # コピー成功メッセージ
                    logger.info(f"ログファイルのバックアップを作成しました: {backup_path}")
                
                # ログファイルを空にする
                with open(LOG_FILE_PATH, "w", encoding="utf-8") as f:
                    f.write("")  # 空のファイルで上書き
                
                # テキストエリアも空にする
                self.log_text.delete(1.0, tk.END)
                self.log_text.insert(tk.END, f"ログをクリアしました。\nバックアップ: {backup_path.name}")
                
                # キャッシュもクリア
                self.__class__._previous_log_content = ""
                
                # 成功メッセージ
                logger.info("ログファイルをクリアしました")
                
                # 成功通知
                messagebox.showinfo("完了", f"ログをクリアしました。\nバックアップが作成されました: {backup_path.name}")
        except Exception as e:
            logger.error(f"ログクリアエラー: {e}")
            messagebox.showerror("エラー", f"ログのクリアに失敗しました: {e}")
            
    def search_logs(self):
        """ログ内を検索して強調表示"""
        # 検索キーワード
        keyword = self.search_var.get()
        if not keyword:
            return
        
        # タグの削除
        self.log_text.tag_remove("search", "1.0", tk.END)
        
        # 大文字小文字を区別しない検索
        start_pos = "1.0"
        while True:
            start_pos = self.log_text.search(keyword, start_pos, tk.END, nocase=True)
            if not start_pos:
                break
            
            end_pos = f"{start_pos}+{len(keyword)}c"
            self.log_text.tag_add("search", start_pos, end_pos)
            start_pos = end_pos
        
        # 検索結果の強調表示
        self.log_text.tag_config("search", background="yellow", foreground="black")


def main():
    """メインエントリーポイント"""
    root = tk.Tk()
    app = KoeMemoGUI(root)
    
    # ウィンドウクローズ時の処理を設定
    root.protocol("WM_DELETE_WINDOW", app.on_closing)
    
    root.mainloop()


if __name__ == "__main__":
    main()
