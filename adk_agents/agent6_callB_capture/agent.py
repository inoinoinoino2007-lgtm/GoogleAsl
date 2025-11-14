
import asyncio
import base64
import logging
import os
import warnings
from datetime import datetime
from io import BytesIO

from google.adk.agents import Agent
from google.adk.agents.callback_context import CallbackContext
from google.adk.agents.loop_agent import LoopAgent
from google.adk.agents.sequential_agent import LlmAgent, SequentialAgent
from google.adk.tools.tool_context import ToolContext
from google import genai
from google.genai.types import Part
from PIL import Image
from selenium import webdriver
from selenium.webdriver.chrome.options import Options

from . import prompt

# Ignore all warnings
warnings.filterwarnings("ignore")

logging.basicConfig(level=logging.ERROR)


logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

GEMINI_MODEL= "gemini-2.5-flash"


def get_date(callback_context: CallbackContext):
    """
    Retrieves a date for today.

    Returns:
        A dict with the date in a formal writing format. For example:
        {"date": "Wednesday, May 7, 2025"}
    """

    today_date = datetime.today().strftime("%A, %B %d, %Y")
    callback_context.state["dateoftoday"] = today_date


def capture_nikkei_screenshot(callback_context: CallbackContext):
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



def analyze_image_from_path(callback_context: CallbackContext):
    """
    画像ファイルパスを指定し、Gemini Visionに説明を要求する最小限の関数。

    Args:
        image_path (str): 説明させたい画像ファイルへのパス。
        prompt (str): 画像に対して求める説明（例: "この画像の内容を説明してください"）。

    Returns:
        str: Geminiが生成した画像の説明テキスト。
    """

    image_path = r"/home/user/kadai_1/kadai1_git/adk_agents/n225_google_finance_screenshot.png" 
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

        callback_context.state["priceoftoday"] = response

    except Exception as e:
        callback_context.state["priceoftoday"] = "None"


# --- Tool Definition ---
def exit_loop(tool_context: ToolContext):
  """Call this function ONLY when the critique indicates no further changes are needed, signaling the iterative process should end."""
  print(f"  [Tool Call] exit_loop triggered by {tool_context.agent_name}")
  tool_context.actions.escalate = True
  # Return empty dict as tools should typically return JSON-serializable output
  return {}


def report_tool():
    """
    ダミーツール
    """
    print("--- ダミーツール動作確認 ---")

    return {}













# エージェント　本日　日付取得
date_agent = LlmAgent(
    name="GetDateAgent",
    model=GEMINI_MODEL,
    instruction=date_agent_prompt,
    description="Provide the date of today using callback function.",
    before_agent_callback = get_date
)

#　エージェント　日経平均のチャートを開いて、スクショ保存
n225_url_agent = LlmAgent(
    name="N225OpenChartAgent",
    model=GEMINI_MODEL,
    description="Save the captured png data of the Nikkei 225(N225) price web page to forecast N225's closing price of the next day.",
    instruction=prompt.n225_url_agent_prompt,
    before_agent_callback = capture_nikkei_screenshot
)

#　エージェント　チャートから本日、前日の日経平均情報取得（画像スクレイピング）
previous_price_agent = LlmAgent(
    name="GetPreviousPriceAgent",
    model=GEMINI_MODEL,
    description="Provide the N225's closing price.",
    instruction=prompt.previous_price_agent_prompt,
    before_agent_callback = analyze_image_from_path
)

#　エージェント　インターネット上から様々な市場情報入手（スクレイピング）
collect_stock_market_news_agent = LlmAgent(
    name="CollectStockMarketNewsAgent",
    model=GEMINI_MODEL,
    instruction=prompt.collect_stock_market_news_agent_prompt,
    description="Gather news articles.",
    output_key="gathered_news" # Stores output in state['gathered_news']
)

# エージェント　初期のN225予想
initial_forecast_N225_agent = LlmAgent(
    name="InitialForecastN225Agent",
    model=GEMINI_MODEL,
    include_contents='none',
    instruction=prompt.initial_forecast_N225_agent_prompt,
    description="Generates a structured forecast of the Nikkei 225 (N225) closing price for the next trading day.",
    output_key="predicted_N225_price"

)

# ループエージェント　N225予想の評価
critic_N225_agent_in_loop = LlmAgent(
    name="CriticForecastN225Agent",
    model=GEMINI_MODEL,
    include_contents='none',
    instruction=prompt.critic_N225_agent_in_loop_prompt,
    description="Reviews the current draft Forecast N225 based on Gathered News Articles & Analysis Basis, providing critique if granulared improvements are needed, otherwise signals completion.",
    output_key="critic_N225"

)

# ループエージェント　N225予想の修正
refiner_agent_in_loop = LlmAgent(
    name="RefinerAgent",
    model="gemini-2.5-flash",
    # Relies solely on state via placeholders
    include_contents='none',
    instruction=prompt.refiner_agent_in_loop_prompt,
    description="Refines the Forecast N225 based on Analysis Summary, or calls exit_loop if the stock price you forecasted has reached a confidence level of 98%",
    tools=[exit_loop], # Provide the exit_loop tool
    output_key= "predicted_N225_price" # Overwrites state['predicted_N225_price'] with the refined version
)

# シーケンシャルエージェント　（日付取得〜初期予想まで）
collect_pipeline_agent = SequentialAgent(
    name="CollectPlineAgent",

    sub_agents=[date_agent,
                n225_url_agent,
                previous_price_agent,
                collect_stock_market_news_agent,
                initial_forecast_N225_agent
                ],
    description="Executes a sequence of confirm current date, check the N225 closing price, gathering financial news, and predicting.",

)
# ループエージェント　（予想評価〜修正出力）
loop_control_agent = LoopAgent(
    name="LoopControlAgent",
    max_iterations = 3,
    sub_agents=[    
                critic_N225_agent_in_loop,
                refiner_agent_in_loop
],
    description="レビューが完了するまでデータ収集とN225終値の予想を繰り返す"
)

final_report_agent = LlmAgent(
    name="FinalAgent",
    model=GEMINI_MODEL,
    instruction=prompt.final_report_agent_prompt,
    description="Generates the final report containing the next day's stock price forecast (close, min, max) and market sentiment, strictly adhering to the specified JSON format.",
    tools = [report_tool]
)

# ルートエージェント
# For ADK tools compatibility, the root agent must be named `root_agent`
root_agent = SequentialAgent(
    name="FlowControlAgent",
    sub_agents=[collect_pipeline_agent,
                loop_control_agent,
                final_report_agent
                ],
    description="日経平均株価 (N225) の当日価格を取得し、処理ループを制御した後、最終レポートを生成するパイプラインを実行するエージェント。"

)
