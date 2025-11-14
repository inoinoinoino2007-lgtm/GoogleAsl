
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

import asyncio
import os
from google.adk.agents import LoopAgent, LlmAgent, BaseAgent, SequentialAgent
from google.genai import types
from google.adk.runners import InMemoryRunner
from google.adk.agents.invocation_context import InvocationContext
from google.adk.tools.tool_context import ToolContext
from typing import AsyncGenerator, Optional
from google.adk.events import Event, EventActions

from google.adk.agents.callback_context import CallbackContext

import logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

GEMINI_MODEL= "gemini-2.5-flash"


# --- Define Sub-Agents for Each Pipeline Stage ---

# 1 Take today info

# def get_date():

def get_date(callback_context: CallbackContext):
    """
    Retrieves a date for today.

    Returns:
        A dict with the date in a formal writing format. For example:
        {"date": "Wednesday, May 7, 2025"}
    """

    today_date = datetime.today().strftime("%A, %B %d, %Y")
    callback_context.state["dateoftoday"] = today_date

# date_agent = LlmAgent(
#     name="TodayAgent",
#     model=GEMINI_MODEL,
#     instruction="""You must use 'get_date' tool to provide the exact date for today in Japan Standard Time. 
#                    This tool procedure is mandatory.""",
#     description="Provide the date of today.",

#     tools = [get_date],
#     output_key="dateoftoday" # Stores output date['dateoftoday']
# )




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


n225_today_price_agent = LlmAgent(
    name="n225_today_price_agent",
    model=GEMINI_MODEL,
    description="Provide the N225's closing price of today to forecast N225's closing price of the next day.",
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
    tools = [capture_nikkei_screenshot, analyze_image_from_path],
    before_agent_callback = get_date
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
        17.Large-Scale Natural Disasters / Earthquake Information:

          Information regarding major earthquakes, typhoons, floods, etc., causing significant damage to specific regions or supply chains (affecting insurance, construction, power stocks, etc.).

        18.Major Corporate Earnings Flashes/Revisions:

          Flash reports on earnings that significantly exceed or fall short of market expectations, or upward/downward revisions to earnings forecasts.

        19.Changes in Major Corporate Management Strategies:

          Announcements regarding business divestiture, large-scale restructuring, or entry into new growth areas.

        20.Statements by CEOs/Presidents of Major Companies:

          Top executives' official views or statements regarding their company's performance outlook, industry prospects, or new ventures.

        21.Official Statements by the US President / Key Government Officials:

          Statements by high-ranking US government officials that directly impact the market, such as those concerning trade policy, tariffs, or foreign policy.

        22.Government Regulation / Legal Amendment Information:

          Information on the introduction of new regulations or proposed amendments to existing laws targeting specific industries (e.g., IT, finance, environment).

        23.Cyberattacks / Large-Scale System Failures:

          Information on cyberattacks targeting major financial institutions or infrastructure companies, or associated service outages.

        24.Pandemic / Infectious Disease Outbreaks:

          Information on the resurgence of large-scale infectious diseases (like COVID-19), the emergence of variants, or declarations of termination.

        25.Overseas Market Trends (Europe, China, etc.):

          Closing prices of major stock indices in Europe (DAX, FTSE) and China's economic indicators (PMI, retail sales).

        26.Sudden Fluctuations in Exchange Rates (vs. Euro, vs. Yuan):

          Rapid changes in major currency pairs other than JPY/USD, affecting the earnings of exporting and importing companies.

        27.Commodity Price Trends (Gold, Copper, Iron Ore):

          Fluctuations in the prices of basic resources directly linked to inflation expectations and material industry costs.

        28.Semiconductor Supply/Demand Information and Inventory Levels:

          Information on lead times, factory utilization rates, and inventory cycles related to semiconductors, which are industry foundations.

        29.Supply Chain Disruption / Resolution Information:

          Information concerning the emergence or resolution of supply constraints for specific components or raw materials.

        30.Individual Investor Activity / SNS Sentiment:

          Trading share of individual investors or the level of discussion regarding specific stocks on social media and forums.

        31.Political Events / Election Results:

          Results of important domestic or major international elections (especially the US), or rapid changes in cabinet approval ratings.

        32.BOJ Purchase Status and Scale (ETFs, J-REITs):

          The scale and timing of confirmed purchases of Exchange-Traded Funds (ETFs) and J-REITs by the Bank of Japan.

        33.Weather Information (Energy/Agricultural Products Related):

          The impact of abnormally high or low temperatures, or droughts, on power demand and agricultural product prices.

        34.Inflation Expectation Market Indicators:

          Indicators such as the Break-Even Inflation Rate (BEI) that show the market's expectation for future inflation.

        35.Analyst Rating Changes:

          Changes in ratings (Buy/Sell) and target prices for individual stocks or sectors by analysts at major securities firms.

        36.Fund Flows of Investment Trusts and Pension Funds:

          Statistical information regarding the inflow or outflow of funds into Japanese stocks by large domestic and international asset managers.


        Output *only* the news articles, enclosed in triple backticks (```news ... ```). 
        Organize the gathered articles by relevant criteria (e.g., country, category) as necessary, and output it in plain text format.
        Output the entire content of the articles including issued date of articles.
        Do not add any other text before or after the code block.

""",
    description="Gather news articles.",
    output_key="gathered_news" # Stores output in state['gathered_news']
)


initial_forecast_N225_agent = LlmAgent(
    name="InitialForecastN225Agent",
    model=GEMINI_MODEL,
    include_contents='none',
    instruction="""
    You are an expert financial strategist specializing in the US and Japanese markets. 
    Write the *first draft* of forecast_N225.
    Your task is to analyze the provided market data and news, and output a detailed forecast for the Nikkei 225 (N225) closing price for the next trading day.

    **[PROVIDED DATA FOR ANALYSIS]**
    Today's Date (JST): {dateoftoday}
    Today's N225 Closing Price: {priceoftoday}
    Gathered News Articles & Analysis Basis: {gathered_news}

    **[MANDATORY PROCEDURE]**
    1. **Analyze** the gathered news sentiment and the impact of the US market's prior close.
    2. **First,** provide a brief analysis of the market action that resulted in today's closing price.
    3. **Second,** state the forecasted closing price for the next trading day, including the Min/Max range.
    4. **3rd,** state the analysis summary in over 800 words.
    4. **The final output MUST strictly adhere to the requested JSON format.**


    **[REQUIRED OUTPUT FORMAT]**(JSON)
    {   
        "forecast_date": "YYYY年MM月DD日",
        "today_close": <float>,
        "forecast_close": <float>,
        "forecast_min": <float>,
        "forecast_max": <float>,
        "market_sentiment": "<Strong Bullish | Neutral | Strong Bearish>",
        "analysis_summary": "<Concise summary of the forecast basis, max 1000 words>"
    }
""",

    description="Generates a structured forecast of the Nikkei 225 (N225) closing price for the next trading day.",
    output_key="predicted_N225_price"

)


# 3 Predict N225 Agent

critic_N225_agent_in_loop = LlmAgent(
    name="CriticForecastN225Agent",
    model=GEMINI_MODEL,
    include_contents='none',
    instruction="""
    You are a Constructive Critic AI reviewing a Forecast N225 Closing Price draft based on **[News Classification and Impact Assessment Criteria]** and **[Evaluation Criteria for Market Psychology and Supply/Demand]**.

    **[PROVIDED DATA FOR Critic]**
    Forecast N225 Closing Price: {priceoftoday}
    Gathered News Articles & Analysis Basis: {gathered_news}


    Output *only* the story/document text. Do not add introductions or explanations.

    **[News Classification and Impact Assessment Criteria]**
    Evaluation of Macro Factors:

    Focus on monetary policy (central bank interest rate decisions, quantitative easing measures, etc.) and economic indicators (GDP, employment statistics, CPI, etc.) to assess their impact on overall market trends and sentiment.

    Evaluate how geopolitical risks (international conflicts, trade friction, etc.) change investor risk appetite.

    Evaluation of Micro Factors:

    Examine how far corporate earnings (sales, profits, EPS) deviate from market expectations.

    Assess the direct impact of capital policies (share buybacks, dividend increases) and M&A on the share prices of individual stocks.

    Evaluation of Surprise Level (Degree of Deviation):

    Evaluate whether the news content is positive or negative compared to market pre-expectations, and assess that the greater the degree of deviation (surprise level), the larger the stock price fluctuation will be.

    Evaluation of Sustainability:

    Evaluate whether the impact of the news is temporary or accompanied by structural and long-term changes (technological innovation, legislative reforms, etc.).

    **[Evaluation Criteria for Market Psychology and Supply/Demand]**
    Impact on Market Sentiment:

    Determine whether the news increases investor risk appetite or spreads anxiety in the market, prompting risk-aversion behavior.

    Impact on Supply and Demand:

    Evaluate how the news influences the trading decisions of large-scale investors such as institutional investors and hedge funds, in conjunction with changes in the short-selling ratio and margin trading ratio (credit multiple).

    Consistency with Technical Analysis:

    Evaluate whether the news can become a factor that breaks through critical turning points in stock prices (resistance lines, support lines, moving averages).
""",
    description="Reviews the current draft Forecast N225 based on Gathered News Articles & Analysis Basis, providing critique if granulared improvements are needed, otherwise signals completion.",
    output_key="critic_N225"

)

# --- Tool Definition ---
def exit_loop(tool_context: ToolContext):
  """Call this function ONLY when the critique indicates no further changes are needed, signaling the iterative process should end."""
  print(f"  [Tool Call] exit_loop triggered by {tool_context.agent_name}")
  tool_context.actions.escalate = True
  # Return empty dict as tools should typically return JSON-serializable output
  return {}


# STEP 2b: Refiner/Exiter Agent (Inside the Refinement Loop)
refiner_agent_in_loop = LlmAgent(
    name="RefinerAgent",
    model="gemini-2.5-flash",
    # Relies solely on state via placeholders
    include_contents='none',
    instruction="""You are a Chief Strategist refining a forecast_N225 based on feedback OR exiting the process.

    **Current Forecast N225:** 
    {predicted_N225_price}

    **Critique/Suggestions:**
    {critic_N225}

    **Task:**ArithmeticError
    Analyze the 'Critique/Suggestions'.

    IF you believe the stock price you forecasted has reached a confidence level of 98%,:
    You MUST call the 'exit_loop' function. Do not output any text.

    ELSE (the confidence level is under 98%):
    Ensure your prediction is always a different numerical value from the previous forecast.
    Carefully apply the suggestions to improve the 'Current Document'. Output *only* the refined document text.

    Do not add explanations. Either output the refined document OR call the exit_loop function.

    **[REQUIRED OUTPUT FORMAT]**(JSON)
    {   
        "forecast_date": "YYYY年MM月DD日",
        "today_close": <float>,
        "forecast_close": <float>,
        "forecast_min": <float>,
        "forecast_max": <float>,
        "market_sentiment": "<Strong Bullish | Neutral | Strong Bearish>",
        "analysis_summary": "<Concise summary of the forecast basis, max 1000 words>"
    }
""",
    description="Refines the Forecast N225 based on Analysis Summary, or calls exit_loop if the stock price you forecasted has reached a confidence level of 98%",
    tools=[exit_loop], # Provide the exit_loop tool
    output_key= "predicted_N225_price" # Overwrites state['predicted_N225_price'] with the refined version
)

# --- 2. Create the SequentialAgent ---
# This agent orchestrates the pipeline by running the sub_agents in order.
collect_pipeline_agent = SequentialAgent(
    name="CollectPlineAgent",

    sub_agents=[
                n225_today_price_agent,
                collect_stock_market_news_agent,
                initial_forecast_N225_agent
                ],
    description="Executes a sequence of confirm current date, check the N225 closing price, gathering financial news, and predicting.",

)

loop_control_agent = LoopAgent(
    name="LoopControlAgent",
    max_iterations = 5,
    sub_agents=[    
                critic_N225_agent_in_loop,
                refiner_agent_in_loop
],
    description="レビューが完了するまでデータ収集とN225終値の予想を繰り返す"
)

def report_tool():
    """
    ダミーツール
    """
    print("--- ダミーツール動作確認 ---")

    return {}

final_report_agent = LlmAgent(
    name="FinalAgent",
    model=GEMINI_MODEL,
    instruction="""You submit the final report based on {predicted_N225_price},

    **[REQUIRED OUTPUT FORMAT]**
    {
        "forecast_date": "YYYY年MM月DD日",
        "today_close": <float>,
        "forecast_close": <float>,
        "forecast_min": <float>,
        "forecast_max": <float>,
        "market_sentiment": "<Strong Bullish | Neutral | Strong Bearish>"
    }
    """,
    description="Generates the final report containing the next day's stock price forecast (close, min, max) and market sentiment, strictly adhering to the specified JSON format.",

    tools = [report_tool]

)

main_pipeline_agent = SequentialAgent(
    name="MainAgent",

    sub_agents=[collect_pipeline_agent,
                loop_control_agent,
                final_report_agent
                ],
    description="日経平均株価 (N225) の当日価格を取得し、処理ループを制御した後、最終レポートを生成するパイプラインを実行するエージェント。"

)
# For ADK tools compatibility, the root agent must be named `root_agent`
root_agent = main_pipeline_agent
