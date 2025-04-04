import base64
import os
import sys

from RAGModel import RAGMultiModalModel
from claudette import *

os.environ["TOKENIZERS_PARALLELISM"] = "false"


RAG = RAGMultiModalModel.from_pretrained("nomic-ai/colnomic-embed-multimodal-7b", verbose=1)

query = "What are the trends in vehicle deliveries?"

pdf_path = "./docs/tesla.pdf"
if not os.path.exists(pdf_path):
    print(f"Error: The file '{pdf_path}' does not exist.")
    print(f"Current working directory: {os.getcwd()}")
    print("Please check that the file path is correct and the file exists.")
    sys.exit(1)


RAG.index(
    input_path=pdf_path,
    index_name="attention",
    store_collection_with_index=True,
    overwrite=True
)

results = RAG.search(query, k=1)

image_bytes = base64.b64decode(results[0].base64)

chat = Chat(models[1])
# models is a claudette helper that contains the list of models available on your account, as of 2024-09-06, [1] is Claude Sonnet 3.5:
result = chat([image_bytes, query])
print(result.content[0].text)