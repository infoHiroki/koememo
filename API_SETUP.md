# APIキーの設定方法

KoeMemoでAI機能を利用するには、以下のいずれかのAPIキーが必要です。

## OpenAI API

1. [OpenAIのウェブサイト](https://platform.openai.com/) にアクセスし、アカウントを作成または既存のアカウントでログインします。
2. 上部メニューから「API Keys」を選択します。
3. 「Create new secret key」ボタンをクリックします。
4. キーに名前を付けて（例: "KoeMemo"）、「Create secret key」をクリックします。
5. 生成されたAPIキーをコピーします（このキーは一度しか表示されません）。
6. KoeMemoの`config.json`ファイルの`llm`セクション内の`api_key`項目にこのキーを貼り付けます。
7. `api_type`を`"openai"`に設定します。

```json
"llm": {
    "api_type": "openai",
    "api_key": "sk-YOUR_OPENAI_API_KEY_HERE",
    "model": "gpt-4o-mini",
    "temperature": 0.3,
    "max_tokens": 1500,
    "google_api_key": ""
}
```

## Anthropic API (Claude)

1. [Anthropicのウェブサイト](https://console.anthropic.com/) にアクセスし、アカウントを作成または既存のアカウントでログインします。
2. コンソールから「API Keys」セクションに移動します。
3. 「Create API Key」ボタンをクリックします。
4. キーに説明を追加し、「Create API Key」をクリックします。
5. 生成されたAPIキーをコピーします。
6. KoeMemoの`config.json`ファイルの`llm`セクション内の`api_key`項目にこのキーを貼り付けます。
7. `api_type`を`"anthropic"`に設定します。

```json
"llm": {
    "api_type": "anthropic",
    "api_key": "sk-ant-YOUR_ANTHROPIC_API_KEY_HERE",
    "model": "claude-3-haiku-20240307",
    "temperature": 0.3,
    "max_tokens": 1500,
    "google_api_key": ""
}
```

## Google Gemini API

1. [Google AI Studioのウェブサイト](https://makersuite.google.com/app/apikey) にアクセスし、Googleアカウントでログインします。
2. 「Get API key」をクリックします。
3. 新しいキーを作成し、コピーします。
4. KoeMemoの`config.json`ファイルの`llm`セクション内の`google_api_key`項目にこのキーを貼り付けます。
5. `api_type`を`"google"`に設定します。

```json
"llm": {
    "api_type": "google",
    "api_key": "",
    "model": "gemini-pro",
    "temperature": 0.3,
    "max_tokens": 1500,
    "google_api_key": "YOUR_GOOGLE_API_KEY_HERE"
}
```

## 注意事項

- APIキーは秘密情報です。他人と共有したり、公開リポジトリにコミットしたりしないでください。
- 各APIプロバイダーの利用規約と料金体系を確認してください。
- `config.json`ファイルはGitリポジトリから除外されています。APIキーを含むこのファイルをコミットしないようにしてください。