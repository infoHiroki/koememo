#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
処理済みファイルビューワー - KoeMemoの処理済みファイルを表示するシンプルなツール
"""

import os
import sys
import json
import tkinter as tk
from tkinter import ttk, messagebox, StringVar
import subprocess
from datetime import datetime
from pathlib import Path

# 設定ファイルのパス
CONFIG_PATH = Path(__file__).parent / "config.json"

class ProcessedFilesViewer:
    def __init__(self, root):
        self.root = root
        self.root.title("KoeMemo - 処理済みファイルビューワー")
        self.root.geometry("900x600")
        
        # 設定ファイルの読み込み
        self.config = self.load_config()
        
        # UI構築
        self.build_ui()
        
    def load_config(self):
        """設定ファイルの読み込み"""
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError) as e:
            messagebox.showerror("エラー", f"設定ファイルの読み込みに失敗しました: {e}")
            return {}
            
    def build_ui(self):
        """UIの構築"""
        # メインフレーム
        main_frame = ttk.Frame(self.root, padding=10)
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # タイトルと説明
        ttk.Label(main_frame, text="処理済みファイルリスト", font=("", 14, "bold")).pack(pady=5)
        ttk.Label(main_frame, text="KoeMemoが処理したファイルの一覧です。ダブルクリックで出力ファイルを開きます。").pack(pady=5)
        
        # 操作フレーム
        control_frame = ttk.Frame(main_frame)
        control_frame.pack(fill=tk.X, pady=5)
        
        # リフレッシュボタン
        ttk.Button(control_frame, text="リスト更新", command=self.refresh_processed_files).pack(side=tk.LEFT, padx=5, pady=5)
        
        # 出力フォルダを開くボタン
        def open_output_dir():
            output_dir = self.config.get("file_watcher", {}).get("output_directory", "")
            if output_dir and os.path.exists(output_dir):
                if sys.platform == "win32":
                    os.startfile(output_dir)
                elif sys.platform == "darwin":  # macOS
                    subprocess.run(["open", output_dir])
                else:  # Linux
                    subprocess.run(["xdg-open", output_dir])
            else:
                messagebox.showwarning("警告", "出力ディレクトリが設定されていないか存在しません。")
        
        ttk.Button(control_frame, text="出力フォルダを開く", command=open_output_dir).pack(side=tk.LEFT, padx=5, pady=5)
        
        # 検索フレーム
        search_frame = ttk.Frame(control_frame)
        search_frame.pack(side=tk.RIGHT, padx=5, pady=5)
        
        ttk.Label(search_frame, text="検索:").pack(side=tk.LEFT, padx=5)
        self.search_var = StringVar()
        search_entry = ttk.Entry(search_frame, textvariable=self.search_var, width=20)
        search_entry.pack(side=tk.LEFT, padx=5)
        search_entry.bind("<KeyRelease>", lambda e: self.filter_processed_files())
        
        # ツリービュー
        tree_frame = ttk.Frame(main_frame)
        tree_frame.pack(fill=tk.BOTH, expand=True, pady=5)
        
        columns = ("filename", "processed_at", "output_file")
        self.tree = ttk.Treeview(tree_frame, columns=columns, show="headings")
        
        # カラム設定
        self.tree.heading("filename", text="元ファイル")
        self.tree.heading("processed_at", text="処理日時")
        self.tree.heading("output_file", text="出力ファイル")
        
        self.tree.column("filename", width=200)
        self.tree.column("processed_at", width=150)
        self.tree.column("output_file", width=450)
        
        scrollbar = ttk.Scrollbar(tree_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # ダブルクリックで出力ファイルを開く
        self.tree.bind("<Double-1>", self.open_output_file)
        
        # 右クリックメニュー
        self.context_menu = tk.Menu(self.tree, tearoff=0)
        self.context_menu.add_command(label="出力ファイルを開く", command=self.open_selected_output)
        self.context_menu.add_command(label="出力フォルダを開く", command=self.open_output_folder)
        self.tree.bind("<Button-3>", self.show_context_menu)
        
        # 初期データ読み込み
        self.refresh_processed_files()
        
    def refresh_processed_files(self):
        """処理済みファイルリストを更新"""
        # 設定を再読み込み（他のプロセスによる変更を反映）
        self.config = self.load_config()
        
        # 既存の項目をクリア
        for item in self.tree.get_children():
            self.tree.delete(item)
        
        # 処理済みファイルリストを取得
        processed_files = self.config.get("processed_files", {})
        if not processed_files:
            # データがない場合は通知を表示
            self.tree.insert("", tk.END, values=("処理済みファイルはありません", "", ""))
            return
        
        # データを整形してツリービューに追加
        items = []
        for file_hash, info in processed_files.items():
            # 出力ファイルパスから元ファイル名を抽出（先頭の部分）
            output_file = info.get("output_file", "")
            output_basename = os.path.basename(output_file)
            
            # "_memo_" の前の部分を取得（元ファイル名として）
            original_name = output_basename.split("_memo_")[0] if "_memo_" in output_basename else "不明"
            
            # 処理日時をフォーマット
            processed_at = info.get("processed_at", "")
            try:
                if processed_at:
                    # ISO形式の日時文字列をdatetimeオブジェクトに変換
                    dt = datetime.fromisoformat(processed_at)
                    # 読みやすい形式に変換
                    processed_at = dt.strftime("%Y-%m-%d %H:%M")
            except Exception:
                processed_at = "不明"
            
            items.append((original_name, processed_at, output_file))
        
        # 日付の新しい順にソート
        items.sort(key=lambda x: x[1], reverse=True)
        
        # ツリービューに追加
        for item in items:
            self.tree.insert("", tk.END, values=item)
        
        # フィルタを適用（検索ボックスに値がある場合）
        self.filter_processed_files()
        
    def filter_processed_files(self):
        """検索条件に基づいて処理済みファイルリストをフィルタリング"""
        search_term = self.search_var.get().lower()
        
        # 検索条件がなければすべて表示
        if not search_term:
            for item in self.tree.get_children():
                self.tree.item(item, tags=())  # タグをリセット
                # 表示
                self.tree.item(item, open=True)
                self.tree.detach(item)  # 一度デタッチ
                self.tree.reattach(item, "", tk.END)  # 再アタッチ
            return
        
        # 各項目をチェックして検索条件に一致するかを確認
        visible_items = []
        for item in self.tree.get_children():
            match = False
            values = self.tree.item(item, "values")
            
            # 値のいずれかに検索語が含まれているか確認
            for value in values:
                if isinstance(value, str) and search_term in value.lower():
                    match = True
                    break
            
            # 一致する項目を表示リストに追加
            if match:
                visible_items.append(item)
                self.tree.item(item, tags=())  # タグをリセット
            else:
                self.tree.item(item, tags=("hidden",))
        
        # すべてのアイテムをデタッチ
        all_items = self.tree.get_children()
        for item in all_items:
            self.tree.detach(item)
        
        # 一致するアイテムのみを再アタッチ
        for item in visible_items:
            self.tree.reattach(item, "", tk.END)
    
    def open_output_file(self, event):
        """ダブルクリックで選択された出力ファイルを開く"""
        item = self.tree.identify("item", event.x, event.y)
        if not item:
            return
            
        values = self.tree.item(item, "values")
        if len(values) >= 3:
            output_file = values[2]
            if output_file and os.path.exists(output_file):
                if sys.platform == "win32":
                    os.startfile(output_file)
                elif sys.platform == "darwin":  # macOS
                    subprocess.run(["open", output_file])
                else:  # Linux
                    subprocess.run(["xdg-open", output_file])
            else:
                messagebox.showwarning("警告", "ファイルが見つかりません。")
    
    def open_selected_output(self):
        """コンテキストメニューから選択された出力ファイルを開く"""
        selected = self.tree.focus()
        if not selected:
            return
            
        values = self.tree.item(selected, "values")
        if len(values) >= 3:
            output_file = values[2]
            if output_file and os.path.exists(output_file):
                if sys.platform == "win32":
                    os.startfile(output_file)
                elif sys.platform == "darwin":  # macOS
                    subprocess.run(["open", output_file])
                else:  # Linux
                    subprocess.run(["xdg-open", output_file])
            else:
                messagebox.showwarning("警告", "ファイルが見つかりません。")
    
    def open_output_folder(self):
        """コンテキストメニューから選択された出力ファイルのフォルダを開く"""
        selected = self.tree.focus()
        if not selected:
            return
            
        values = self.tree.item(selected, "values")
        if len(values) >= 3:
            output_file = values[2]
            if output_file:
                output_dir = os.path.dirname(output_file)
                if os.path.exists(output_dir):
                    if sys.platform == "win32":
                        os.startfile(output_dir)
                    elif sys.platform == "darwin":  # macOS
                        subprocess.run(["open", output_dir])
                    else:  # Linux
                        subprocess.run(["xdg-open", output_dir])
                else:
                    messagebox.showwarning("警告", "フォルダが見つかりません。")
    
    def show_context_menu(self, event):
        """右クリックでコンテキストメニューを表示"""
        item = self.tree.identify("item", event.x, event.y)
        if item:
            self.tree.selection_set(item)
            self.context_menu.post(event.x_root, event.y_root)
            
def main():
    root = tk.Tk()
    app = ProcessedFilesViewer(root)
    root.mainloop()

if __name__ == "__main__":
    main()