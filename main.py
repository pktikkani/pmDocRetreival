import base64
import io
import os
import re
import sys
import time

from openai import OpenAI

from RAGModel import RAGMultiModalModel
from claudette import *


os.environ["TOKENIZERS_PARALLELISM"] = "false"

client = OpenAI()

RAG = RAGMultiModalModel.from_pretrained("nomic-ai/colnomic-embed-multimodal-7b", verbose=1)

query = "what is the document about ..?"

pdf_path = "./docs/NTS.pdf"
if not os.path.exists(pdf_path):
    print(f"Error: The file '{pdf_path}' does not exist.")
    print(f"Current working directory: {os.getcwd()}")
    print("Please check that the file path is correct and the file exists.")
    sys.exit(1)



RAG.index(
    input_path=pdf_path,
    index_name="vllm_index",
    store_collection_with_index=True,
    overwrite=True,
)

results = RAG.search(query, k=1)

image_bytes = base64.b64decode(results[0].base64)


#
chat = Chat(models[1])
# models is a claudette helper that contains the list of models available on your account, as of 2024-09-06, [1] is Claude Sonnet 3.5:
result = chat([image_bytes, query])
print(result.content[0].text)

## Open AI Bits

# base64_image = base64.b64encode(image_bytes).decode('utf-8')
# image_format = "jpeg" # <--- ASSUMPTION: Change if needed!
# data_uri = f"data:image/{image_format};base64,{base64_image}"
# print(f"Prepared image data URI for OpenAI (format assumed: {image_format}).")
#
# messages = [
#     {
#         "role": "user",
#         "content": [
#             # First part: the text query
#             {"type": "text", "text": query},
#             # Second part: the image
#             {
#                 "type": "image_url",
#                 "image_url": {"url": data_uri}
#              }
#         ]
#     }
# ]
#
# response = client.chat.completions.create(
#         model="gpt-4o",
#         messages=messages,
#         max_tokens=1000 # Adjust max_tokens as needed for expected response length
#     )
# # 5. Process the response
# result_text = response.choices[0].message.content
# print("--- OpenAI Response Received ---")
# print(result_text)







