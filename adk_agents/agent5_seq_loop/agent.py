
from google.adk.agents import Agent
from google.adk.agents.sequential_agent import SequentialAgent, LlmAgent
import pandas as pd
from GoogleNews import GoogleNews # GoogleNewsなどの必要なライブラリもインポート
import json
from google import genai
from google.genai.errors import APIError
from google.adk.tools import google_search
from datetime import datetime, timedelta
import dateparser

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
import os

import base64
from io import BytesIO
from PIL import Image
import os
from google import genai
from google.genai.types import Part


import logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

GEMINI_MODEL= "gemini-2.0-flash"
# --- Define Sub-Agents for Each Pipeline Stage ---

# 1 Take today info

# def get_date():

def get_date():
    """
    Retrieves a date for today.

    Returns:
        A dict with the date in a formal writing format. For example:
        {"date": "Wednesday, May 7, 2025"}
    """

    today_date = datetime.today().strftime("%A, %B %d, %Y")
    return {"date": today_date}

date_agent = LlmAgent(
    name="TodayAgent",
    model=GEMINI_MODEL,
    instruction="""You must use 'get_date' tool to provide the exact date for today in Japan Standard Time. 
                   This tool procedure is mandatory.""",
    description="Provide the date of today.",

    tools = [get_date],
    output_key="dateoftoday" # Stores output date['dateoftoday']
)




def capture_nikkei_screenshot():
    """
    指定されたGoogle FinanceのURLを開き、スクリーンショットを撮影・保存します。
    """
    print(f"--- 1. WebDriver設定 ---")

    # --- 実行部分 ---
    url = "https://www.google.com/finance/quote/NI225:INDEXNIKKEI"
    filename = "n225_google_finance_screenshot.png"
    # 1. Chromeオプションの設定
    chrome_options = Options()
    print("2")
    # 💡 サーバー環境で必須の設定 (画面を表示しない「ヘッドレスモード」)
    chrome_options.add_argument("--headless") 
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    print("3")
    # 画面サイズを設定（このサイズでスクリーンショットが撮影されます）
    chrome_options.add_argument("--window-size=1920,1080")

    # 2. WebDriverの初期化と実行
    driver = None # エラー時にもdriverを閉じられるように初期化
    try:
        # WebDriverを起動
        # 💡 注意: ColabやGCP Notebooksではこれで動きますが、ローカル環境では
        # ChromeDriverのパス指定が必要な場合があります。
        driver = webdriver.Chrome(options=chrome_options)

        print(f"--- 2. ページアクセス ---")
        driver.get(url)

        # ページが完全に読み込まれるまで少し待機（必須ではありませんが安定します）
        # driver.implicitly_wait(5) 

        # 3. スクリーンショットの撮影と保存
        driver.save_screenshot(filename)

        print(f"✅ 撮影完了！ファイル名: {filename}")
        if os.path.exists(filename):
            print(f"ファイルサイズ: {os.path.getsize(filename) / 1024:.2f} KB")

    except Exception as e:
        print(f"❌ エラーが発生しました。原因: {e}")
        print("環境にChrome/ChromeDriverが正しくインストールされているか確認してください。")

    finally:
        # 処理を終える際には、必ずブラウザを閉じる（リソース解放）
        if driver:
            driver.quit()

# def analyze_image_from_path(image_path: str, prompt: str) -> str:
def analyze_image_from_path():
    """
    画像ファイルパスを指定し、Gemini Visionに説明を要求する最小限の関数。

    Args:
        image_path (str): 説明させたい画像ファイルへのパス。
        prompt (str): 画像に対して求める説明（例: "この画像の内容を説明してください"）。

    Returns:
        str: Geminiが生成した画像の説明テキスト。
    """

    image_path = "n225_google_finance_screenshot.png" 
    prompt = "この画像はN225株価です。表示されている株価の値をJSON形式で抽出してください。"

    if not os.path.exists(image_path):
        return f"エラー: ファイルが見つかりません: {image_path}"

    # 1. 画像ファイルを読み込み、Base64エンコード
    img = Image.open(image_path)
    buffer = BytesIO()
    img.save(buffer, format="PNG") 
    image_bytes = buffer.getvalue()

    # 2. Geminiの Part オブジェクトを作成
    image_part = Part.from_bytes(
        data=image_bytes,
        mime_type='image/png' 
    )

    # clientは外部で定義されている前提
    client = genai.Client()
    # 3. Gemini APIを呼び出し
    try:
        response = client.models.generate_content(
            model='gemini-2.5-flash', 
            contents=[
                prompt,         # テキストプロンプト
                image_part      # 画像データ
            ]
        )
        return response.text

    except Exception as e:
        return f"API呼び出しエラー: {e}"


# # --- ウェブニュースN225の前日実績取り込み ---
# capture_nikkei_screenshot(URL_TO_CAPTURE, OUTPUT_FILENAME)

# # --- 実行シミュレーション（クライアントとファイルパスは別途準備が必要） ---
# description = analyze_image_from_path()
# print(description)

n225_today_price_agent = LlmAgent(
    name="n225_today_price_agent",
    model=GEMINI_MODEL,
    description="Provide the N225's closing price of today.",
    instruction="""Provide the the N225's preliminary closing price or exactly N225's closing price of today from the internet. 
                   The following tool procedure is mandatory and must be executed step-by-step
                   1st: You must use the 'capture_nikkei_screenshot' tool to capture the Nikkei 225(N225) price web page.
                   2nd: You must use the 'analyze_image_from_path' tool to get the Nikkei 225(N225) closing price.

    **today's date**
    {dateoftoday}

    **[OUTPUT FORMAT e.g.]**
    ```json
    {
    "stock_name": "Nikkei 225",
    "current_value": 50911.76,
    "previous_close": 50276.37,
    "day_range": {
        "low": 50392.44,
        "high": 50969.50
    },
    "year_range": {
        "low": 30792.74,
        "high": 52411.34
    },
    "as_of_date_time": "Nov 11, 4:16:06 AM GMT+9"
    }
    ```

    """,    
    output_key="priceoftoday", # Stores output date['priceoftoday']
    tools = [capture_nikkei_screenshot, analyze_image_from_path]
)


# 2 Collect the stock market news Agent
# Takes the initial specification (from user query) and collect the stock market news by Google search.
collect_stock_market_news_agent = LlmAgent(
    name="CollectStockMarketNewsAgent",
    model=GEMINI_MODEL,
    instruction="""You are the Chief Strategist at a brokerage firm , specializing in the US and Japanese markets.
        Based *only* on the user's request, gather news articles from the internet that could potentially impact the Nikkei 225 (N225).
        Please gather news from {dateoftoday} back to five days ago.

        **[Key Factors for N225 Forecast (e.g., add other relevant items as necessary)]**
        1.US - Economy/Federal Reserve
        2.US Major Index Closes (S&P 500, NASDAQ, Dow)
        3.US Long-Term Treasury Yields
        4.USD/JPY Exchange Rat
        5.Crude Oil Prices (WTI/Brent)
        6.Japan - Economy/Monetary Policy
        7.BOJ Monetary Policy Decisions
        8.Corporate Earnings and Outlooks
        9.Economic Indicators (GDP, CPI)
        10.Investor Trading Activity (by Type)
        11.Sentiment and Technical Factors
        12.VIX Index (Volatility Index)
        13.Geopolitical Events
        14.N225 Technical Analysis (e.g., Support/Resistance)
        15.Market Sentiment Score
        16.N225 Index Closes

        Output *only* the news articles, enclosed in triple backticks (```news ... ```). 
        Organize the gathered articles by relevant criteria (e.g., country, category) as necessary, and output it in plain text format.
        Output the entire content of the articles including issued date of articles.
        Do not add any other text before or after the code block.

""",
    description="Gather news articles.",
    output_key="gathered_news" # Stores output in state['gathered_news']
)

# 3 Predict N225 Agent

predict_N225_agent = LlmAgent(
    name="PredictN225Agent",
    model=GEMINI_MODEL,

    instruction="""
    You are an expert financial strategist specializing in the US and Japanese markets. 
    Your task is to analyze the provided market data and news, and output a detailed forecast for the Nikkei 225 (N225) closing price for the next trading day.

    **[PROVIDED DATA FOR ANALYSIS]**
    Today's Date (JST): {dateoftoday}
    Today's N225 Closing Price: {priceoftoday}
    Gathered News Articles & Analysis Basis: {gathered_news}

    **[MANDATORY PROCEDURE]**
    1. **Analyze** the gathered news sentiment and the impact of the US market's prior close.
    2. **First,** provide a brief analysis of the market action that resulted in today's closing price.
    3. **Second,** state the forecasted closing price for the next trading day, including the Min/Max range.
    4. **The final output MUST strictly adhere to the requested JSON format.**


    **[REQUIRED OUTPUT FORMAT]**
    {
        "forecast_date": "YYYY年MM月DD日",
        "today_close": <float>,
        "forecast_close": <float>,
        "forecast_min": <float>,
        "forecast_max": <float>,
        "market_sentiment": "<Strong Bullish | Neutral | Strong Bearish>",
        "analysis_summary": "<Concise summary of the forecast basis, max 100 words>"
    }
""",

    description="Generates a structured forecast of the Nikkei 225 (N225) closing price for the next trading day.",
    output_key="predicted_N225_price"

)



# --- 2. Create the SequentialAgent ---
# This agent orchestrates the pipeline by running the sub_agents in order.
forecast_pipeline_agent = SequentialAgent(
    name="N225ForecastPipelineAgent",

    sub_agents=[date_agent, 
                n225_today_price_agent, 
                collect_stock_market_news_agent, 
                predict_N225_agent],
    description="Executes a sequence of confirm current date, check the N225 closing price, gathering financial news, and predicting.",
    # instruction="Orchestrates the N225 forecasting pipeline in sequential order: Date -> Price -> News -> Prediction."
)

# For ADK tools compatibility, the root agent must be named `root_agent`
root_agent = forecast_pipeline_agent
