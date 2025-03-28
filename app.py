from typing import Any
import os
from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler
import snowflake.connector
import pandas as pd
from snowflake.core import Root
from dotenv import load_dotenv
import matplotlib
import matplotlib.pyplot as plt
from snowflake.snowpark import Session
import numpy as np
import time
import requests
import datetime
from cortex_chat import CortexChat

matplotlib.use('Agg')
load_dotenv()

ACCOUNT = os.getenv("ACCOUNT")
HOST = os.getenv("HOST")
USER = os.getenv("DEMO_USER")
DATABASE = os.getenv("DEMO_DATABASE")
SCHEMA = os.getenv("DEMO_SCHEMA")
ROLE = os.getenv("DEMO_USER_ROLE")
WAREHOUSE = os.getenv("WAREHOUSE")
SLACK_APP_TOKEN = os.getenv("SLACK_APP_TOKEN")
SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN")
AGENT_ENDPOINT = os.getenv("AGENT_ENDPOINT")
RSA_PRIVATE_KEY_PATH = os.getenv("RSA_PRIVATE_KEY_PATH")
MODEL = os.getenv("MODEL")

DEBUG = False

# Initializes app
app = App(token=SLACK_BOT_TOKEN)
messages = []

# Track user interactions by day
user_last_interaction = {}


@app.message("hello")
def message_hello(message, say):
    say(f"Hey there <@{message['user']}>!")

    hello_message = """
    I'm your AI Analyst. I've already crunched the numbers on your greeting and can confirm it's 99.9% awesome. Still room to improve :sweat_smile: Ready to crunch some numbers together?"
    """

    say(hello_message)


@app.event("message")
def handle_message_events(ack, body, say):
    try:
        ack()
        prompt = body['event']['text']
        user_id = body['event']['user']

        # Check if this is the first interaction today for this user
        current_date = datetime.datetime.now().date()
        show_warning = False

        if user_id not in user_last_interaction:
            show_warning = True
        else:
            last_interaction_date = user_last_interaction[user_id]
            if last_interaction_date != current_date:
                show_warning = True

        # Update the last interaction timestamp for this user
        user_last_interaction[user_id] = current_date

        # Show AI warning if this is the first interaction today
        if show_warning:
            say(
                text="AI Assistant Warning",
                blocks=[
                    {
                        "type": "header",
                        "text": {
                            "type": "plain_text",
                            "text": ":warning: AI Assistant Important Notice :warning:",
                            "emoji": True
                        }
                    },
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": "This AI assistant uses automated systems to provide information. While we strive for accuracy, please note:\n\n• Information may not always be accurate or complete\n• Always verify important information\n• The AI will have limitations\n\nPlease use your judgment when acting on the information provided."
                        }
                    },
                    {
                        "type": "divider"
                    }
                ]
            )

        say(
            text="AI is generating a response",
            blocks=[
                {
                    "type": "divider"
                },
                {
                    "type": "section",
                    "text": {
                        "type": "plain_text",
                        "text": ":brain: AI Analyst is generating a response. Please wait...",
                    }
                },
                {
                    "type": "divider"
                },
            ]
        )
        response = ask_agent(prompt)
        display_agent_response(response, say)
    except Exception as e:
        error_info = f"{type(e).__name__} at line {e.__traceback__.tb_lineno} of {__file__}: {e}"
        print(error_info)
        say(
            text="Request failed...",
            blocks=[
                {
                    "type": "divider"
                },
                {
                    "type": "section",
                    "text": {
                        "type": "plain_text",
                        "text": f"{error_info}",
                    }
                },
                {
                    "type": "divider"
                },
            ]
        )


def ask_agent(prompt):
    resp = CORTEX_APP.chat(prompt)
    return resp


def display_agent_response(content, say):
    if content.get('sql'):
        sql = content['sql']
        # Execute SQL query and get result with snowflake cursor
        cursor = CONN.cursor()
        cursor.execute(sql)

        # Convert the result to a pandas DataFrame
        result = cursor.fetchall()
        columns = [desc[0] for desc in cursor.description]
        df = pd.DataFrame(result, columns=columns)
        cursor.close()

        # Display the table result
        say(
            text="Answer:",
            blocks=[
                {
                    "type": "rich_text",
                    "elements": [
                        {
                            "type": "rich_text_quote",
                            "elements": [
                                {
                                    "type": "text",
                                    "text": "Answer:",
                                    "style": {
                                        "bold": True
                                    }
                                }
                            ]
                        },
                        {
                            "type": "rich_text_preformatted",
                            "elements": [
                                {
                                    "type": "text",
                                    "text": f"{df.to_string()}"
                                }
                            ]
                        }
                    ]
                }
            ]
        )

        # Determine if a chart should be created based on the text content
        text = content.get('text', '').lower()
        chart_type = None

        # Check for specific visualization requests in the query response
        if 'pie chart' in text or 'pie graph' in text:
            chart_type = 'pie'
        elif 'bar chart' in text or 'bar graph' in text:
            chart_type = 'bar'
        elif 'line chart' in text or 'line graph' in text or 'trend' in text:
            chart_type = 'line'
        elif 'scatter' in text or 'correlation' in text or 'relationship between' in text:
            chart_type = 'scatter'

        # Only create chart if there's enough data
        if len(df.columns) > 1 and len(df) > 0:
            # If a specific chart type was requested or if it seems appropriate for visualization
            if chart_type or 'visual' in text or 'chart' in text or 'graph' in text or 'plot' in text:
                chart_img_url = None
                try:
                    # Use detected chart type or default to pie chart
                    chart_img_url = plot_chart(df, chart_type or 'pie')
                except Exception as e:
                    error_info = f"{type(e).__name__} at line {e.__traceback__.tb_lineno} of {__file__}: {e}"
                    print(f"Warning: Data likely not suitable for displaying as a chart. {error_info}")

                if chart_img_url is not None:
                    # Determine chart type name for display
                    display_type = chart_type.capitalize() if chart_type else "Data"

                    say(
                        text=f"{display_type} Chart",
                        blocks=[
                            {
                                "type": "image",
                                "title": {
                                    "type": "plain_text",
                                    "text": f"{display_type} Chart Visualization"
                                },
                                "block_id": "image",
                                "slack_file": {
                                    "url": f"{chart_img_url}"
                                },
                                "alt_text": f"{display_type} Chart"
                            }
                        ]
                    )
    else:
        # Check if the response is just a generic assistant message without useful content
        text = content.get('text', '').strip()
        citations = content.get('citations', '').strip()

        # Only show the citation section if there are actual citations
        citation_block = []
        if citations:
            citation_block = [
                {
                    "type": "rich_text_quote",
                    "elements": [
                        {
                            "type": "text",
                            "text": f"* Citation: {citations}",
                            "style": {
                                "italic": True
                            }
                        }
                    ]
                }
            ]

        say(
            text="Answer:",
            blocks=[
                {
                    "type": "rich_text",
                    "elements": [
                        {
                            "type": "rich_text_quote",
                            "elements": [
                                {
                                    "type": "text",
                                    "text": f"Answer: {text}",
                                    "style": {
                                        "bold": True
                                    }
                                }
                            ]
                        },
                        *citation_block
                    ]
                }
            ]
        )


def plot_chart(df, chart_type='pie'):
    """
    Create charts based on dataframe and requested chart type.
    Supported chart types: pie, bar, line, scatter

    Args:
        df: Pandas DataFrame with the data to plot
        chart_type: Type of chart to create (default: pie)

    Returns:
        URL to the uploaded chart image in Slack
    """
    plt.figure(figsize=(10, 6), facecolor='#333333')

    # Set text color for all elements
    plt.rcParams['text.color'] = 'white'
    plt.rcParams['axes.labelcolor'] = 'white'
    plt.rcParams['xtick.color'] = 'white'
    plt.rcParams['ytick.color'] = 'white'

    # Determine what kind of chart to create based on prompt
    if chart_type.lower() == 'pie':
        # Pie chart (default)
        plt.pie(df[df.columns[1]],
                labels=df[df.columns[0]],
                autopct='%1.1f%%',
                startangle=90,
                colors=['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd', '#8c564b'],
                textprops={'color': "white", 'fontsize': 12})
        plt.axis('equal')  # Equal aspect ratio ensures that pie is drawn as a circle
        plt.title(f'{df.columns[1]} by {df.columns[0]}', color='white', fontsize=14)

    elif chart_type.lower() == 'bar':
        # Bar chart
        ax = plt.subplot(111)
        ax.bar(df[df.columns[0]], df[df.columns[1]], color='#1f77b4')
        plt.xlabel(df.columns[0], fontsize=12)
        plt.ylabel(df.columns[1], fontsize=12)
        plt.title(f'{df.columns[1]} by {df.columns[0]}', color='white', fontsize=14)
        plt.xticks(rotation=45, ha='right')
        ax.set_facecolor('#333333')

    elif chart_type.lower() == 'line':
        # Line chart
        ax = plt.subplot(111)
        ax.plot(df[df.columns[0]], df[df.columns[1]], marker='o', color='#1f77b4')
        plt.xlabel(df.columns[0], fontsize=12)
        plt.ylabel(df.columns[1], fontsize=12)
        plt.title(f'{df.columns[1]} over {df.columns[0]}', color='white', fontsize=14)
        plt.xticks(rotation=45, ha='right')
        ax.set_facecolor('#333333')
        plt.grid(True, alpha=0.3)

    elif chart_type.lower() == 'scatter':
        # Scatter plot (requires at least 3 columns)
        if len(df.columns) >= 3:
            ax = plt.subplot(111)
            scatter = ax.scatter(df[df.columns[0]], df[df.columns[1]],
                                 c=df[df.columns[2]] if len(df.columns) > 2 else None,
                                 s=100,
                                 alpha=0.7,
                                 cmap='viridis')
            plt.xlabel(df.columns[0], fontsize=12)
            plt.ylabel(df.columns[1], fontsize=12)
            plt.title(f'Relationship between {df.columns[0]} and {df.columns[1]}', color='white', fontsize=14)
            if len(df.columns) > 2:
                plt.colorbar(scatter, label=df.columns[2])
            ax.set_facecolor('#333333')
            plt.grid(True, alpha=0.3)
        else:
            # Fallback to scatter plot with just 2 columns
            ax = plt.subplot(111)
            ax.scatter(df[df.columns[0]], df[df.columns[1]], color='#1f77b4', s=100, alpha=0.7)
            plt.xlabel(df.columns[0], fontsize=12)
            plt.ylabel(df.columns[1], fontsize=12)
            plt.title(f'Relationship between {df.columns[0]} and {df.columns[1]}', color='white', fontsize=14)
            ax.set_facecolor('#333333')
            plt.grid(True, alpha=0.3)

    else:
        # Default to bar chart if unknown type
        ax = plt.subplot(111)
        ax.bar(df[df.columns[0]], df[df.columns[1]], color='#1f77b4')
        plt.xlabel(df.columns[0], fontsize=12)
        plt.ylabel(df.columns[1], fontsize=12)
        plt.title(f'{df.columns[1]} by {df.columns[0]}', color='white', fontsize=14)
        plt.xticks(rotation=45, ha='right')
        ax.set_facecolor('#333333')

    # Set the background color for the plot area to dark
    plt.gca().set_facecolor('#333333')
    plt.tight_layout()

    # save the chart as a .jpg file
    file_path_jpg = f'{chart_type}_chart.jpg'
    plt.savefig(file_path_jpg, format='jpg', facecolor='#333333')
    file_size = os.path.getsize(file_path_jpg)

    # upload image file to slack
    file_upload_url_response = app.client.files_getUploadURLExternal(filename=file_path_jpg, length=file_size)
    if DEBUG:
        print(file_upload_url_response)
    file_upload_url = file_upload_url_response['upload_url']
    file_id = file_upload_url_response['file_id']
    with open(file_path_jpg, 'rb') as f:
        response = requests.post(file_upload_url, files={'file': f})

    # check the response
    img_url = None
    if response.status_code != 200:
        print("File upload failed", response.text)
    else:
        # complete upload and get permalink to display
        response = app.client.files_completeUploadExternal(files=[{"id": file_id, "title": f"{chart_type} chart"}])
        if DEBUG:
            print(response)
        img_url = response['files'][0]['permalink']
        time.sleep(2)

    return img_url


def init():
    conn, jwt, cortex_app = None, None, None

    conn = snowflake.connector.connect(
        user=USER,
        authenticator="SNOWFLAKE_JWT",
        private_key_file=RSA_PRIVATE_KEY_PATH,
        account=ACCOUNT,
        warehouse=WAREHOUSE,
        role=ROLE,
        host=HOST
    )
    if not conn.rest.token:
        print(">>>>>>>>>> Snowflake connection unsuccessful!")

    # Collect semantic models using a generic approach
    semantic_models = []

    # Look for any environment variables ending with _SEMANTIC_MODEL
    for key, value in os.environ.items():
        if key.endswith("_SEMANTIC_MODEL") and value:
            model = value.strip()
            if model and model not in semantic_models:
                semantic_models.append(model)
                print(f"Found semantic model ({key}): {model}")

    # Collect search services using the same approach
    search_services = []

    # Look for any environment variables ending with _SEARCH_SERVICE
    for key, value in os.environ.items():
        if key.endswith("_SEARCH_SERVICE") and value:
            service = value.strip()
            if service and service not in search_services:
                search_services.append(service)
                print(f"Found search service ({key}): {service}")

    # Create the CortexChat instance with all parameters
    if len(semantic_models) == 0:
        print("WARNING: No semantic models found in environment variables!")
    else:
        print(f"Using semantic models: {semantic_models}")

    if len(search_services) == 0:
        print("WARNING: No search services found in environment variables!")
    else:
        print(f"Using search services: {search_services}")

    cortex_app = CortexChat(
        agent_url=AGENT_ENDPOINT,
        search_services=search_services,
        semantic_models=semantic_models,
        model=MODEL,
        account=ACCOUNT,
        user=USER,
        private_key_path=RSA_PRIVATE_KEY_PATH
    )

    print(">>>>>>>>>> Init complete")
    return conn, jwt, cortex_app


# Start app
if __name__ == "__main__":
    CONN, JWT, CORTEX_APP = init()
    Root = Root(CONN)
    SocketModeHandler(app, SLACK_APP_TOKEN).start()