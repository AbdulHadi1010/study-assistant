"""Generate the Study Assistant AWS architecture diagram (docs/architecture.png).

Dev-only: needs `pip install -r requirements-dev.txt` and Graphviz (https://graphviz.org/download/).
Run: python scripts/make_diagram.py
"""
from pathlib import Path

from diagrams import Cluster, Diagram, Edge, Node
from diagrams.aws.compute import Lambda
from diagrams.aws.database import Dynamodb
from diagrams.aws.general import Client, User
from diagrams.aws.ml import Bedrock, Polly
from diagrams.aws.security import SecretsManager
from diagrams.onprem.network import Internet
from diagrams.programming.language import Python

OUTPUT = str(Path(__file__).resolve().parent.parent / "docs" / "architecture")  # diagrams adds ".png"

graph_attr = {
    "splines": "spline",
    "nodesep": "1.3",
    "ranksep": "2.4",
    "pad": "0.8",
    "fontname": "Helvetica",
    "fontsize": "26",
    "labelloc": "t",
    "bgcolor": "white",
    "dpi": "140",
    "mclimit": "20",       # search harder for an arrangement with no crossing arrows
    "remincross": "true",
}
node_attr = {"fontname": "Helvetica", "fontsize": "14"}
edge_attr = {"fontname": "Helvetica", "fontsize": "13", "color": "#5A6B7B", "fontcolor": "#1F2D3D", "penwidth": "1.6"}
cluster_style = {"fontname": "Helvetica Bold", "fontsize": "15", "margin": "28"}

GREEN, ORANGE, GREY = "#01A88D", "#E7871B", "#5A6B7B"


def flow(label: str, color: str = GREY, **extra) -> Edge:
    return Edge(label=f"  {label}  ", color=color, fontcolor=color if color != GREY else "#1F2D3D", **extra)


with Diagram(
    "Study Assistant: AWS Architecture",
    filename=OUTPUT,
    outformat="png",
    show=False,
    direction="LR",
    graph_attr=graph_attr,
    node_attr=node_attr,
    edge_attr=edge_attr,
):
    student = User("Student")

    with Cluster("Student's laptop", graph_attr=cluster_style):
        with Cluster("Frontend", graph_attr=cluster_style):
            ui = Client("Streamlit chat UI\nstreamlit_app.py\nvoice.py")
        with Cluster("Python backend", graph_attr=cluster_style):
            agent = Python("Agent loop\nagent_client.py")

    with Cluster("AWS Cloud (us-east-1)", graph_attr=cluster_style):
        with Cluster("AI model", graph_attr=cluster_style):
            bedrock = Bedrock("Amazon Bedrock\nNova Pro")

        with Cluster("Tools stack (CloudFormation)", graph_attr=cluster_style):
            tools = Lambda("AWS Lambda\nstudy-assistant-tools")
            dynamo = Dynamodb("Amazon DynamoDB\ncourses and marks")
            secrets = SecretsManager("Secrets Manager\nTodoist token")

        with Cluster("Voice", graph_attr=cluster_style):
            polly = Polly("Amazon Polly\nvoice replies")

    with Cluster("External service", graph_attr=cluster_style):
        todoist = Internet("Todoist API\nto-do list")

    note = Node(
        "Steps 3 to 6 repeat until Nova writes the final answer\n"
        "(at most 8 tool rounds). Nova never calls Lambda itself:\n"
        "it only asks, and the agent loop runs the tool.",
        shape="note", style="filled", fillcolor="#FFF8E1", color="#E0C27A",
        fontname="Helvetica", fontsize="13", width="5", height="1.2", labelloc="c", imagescale="false",
    )

    student >> flow("1. types a question") >> ui
    ui >> flow("2. message") >> agent
    ui << flow("8. answer, word by word") << agent

    agent >> flow("3. conversation + tool list", GREEN) >> bedrock
    agent << flow("4. tool request (or final answer)", GREEN) << bedrock

    agent >> flow("5. invoke tool", ORANGE) >> tools
    agent << flow("6. tool result", ORANGE) << tools

    tools >> flow("read / write") >> dynamo
    tools >> flow("read token") >> secrets
    tools >> flow("HTTPS") >> todoist

    ui >> flow("9. speak reply (optional)", GREEN) >> polly

    ui >> Edge(style="invis") >> note
