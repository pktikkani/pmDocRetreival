from bs4 import Script
from fasthtml.common import *
import os
import base64
import uuid
import io
from pathlib import Path
from PIL import Image
from fasthtml.js import MarkdownJS
from RAGModel import RAGMultiModalModel
from claudette import Chat, models

os.environ["TOKENIZERS_PARALLELISM"] = "false"

# Initialize the RAG model
RAG = RAGMultiModalModel.from_pretrained("nomic-ai/colnomic-embed-multimodal-7b", verbose=1)

# Create a directory for uploads if it doesn't exist
uploads_dir = Path("uploads")
uploads_dir.mkdir(exist_ok=True)

# Create a static directory for images if it doesn't exist



# # Function to resize an image to fit within Claude's 5MB limit
def resize_image_for_claude(image_bytes):
    """
    Resize an image to fit within Claude's 5MB limit with a safety margin
    """
    # Load the image from bytes
    img = Image.open(io.BytesIO(image_bytes))

    # Define max size (4.7MB to allow for overhead when sending)
    MAX_SIZE_BYTES = 4.7 * 1024 * 1024

    # Start with original size
    quality = 90  # Start with slightly lower quality
    output = io.BytesIO()

    # Try to compress the image while keeping its dimensions
    img.save(output, format='JPEG', quality=quality)

    # If the image is still too large, reduce quality
    while output.tell() > MAX_SIZE_BYTES and quality > 10:
        output = io.BytesIO()
        quality -= 10
        print(f"Reducing image quality to {quality}")
        img.save(output, format='JPEG', quality=quality)

    # If reducing quality didn't work, resize the image
    if output.tell() > MAX_SIZE_BYTES:
        # Calculate new dimensions while maintaining aspect ratio
        aspect = img.width / img.height

        # Start with a reasonable reduction
        scale_factor = 0.8
        new_width = int(img.width * scale_factor)
        new_height = int(new_width / aspect)

        while output.tell() > MAX_SIZE_BYTES and new_width > 100:
            # Resize the image
            print(f"Resizing image to {new_width}x{new_height}")
            resized_img = img.resize((new_width, new_height), Image.LANCZOS)

            # Save to buffer
            output = io.BytesIO()
            resized_img.save(output, format='JPEG', quality=quality)

            # Further reduce dimensions if needed
            scale_factor *= 0.8
            new_width = int(img.width * scale_factor)
            new_height = int(new_width / aspect)

    # Final size check
    output.seek(0)
    final_size = output.tell()
    print(f"Final image size: {final_size / (1024 * 1024):.2f} MB")

    if final_size > 5 * 1024 * 1024:
        print("Warning: Image is still too large for Claude API")

        # Last resort: force a smaller size with lower quality
        output = io.BytesIO()
        max_dimension = 1000  # Set a hard maximum dimension
        if img.width > img.height:
            new_size = (max_dimension, int(max_dimension / aspect))
        else:
            new_size = (int(max_dimension * aspect), max_dimension)

        resized_img = img.resize(new_size, Image.LANCZOS)
        resized_img.save(output, format='JPEG', quality=60)
        output.seek(0)
        print(f"Emergency resize: {output.tell() / (1024 * 1024):.2f} MB")

    return output.getvalue()


hdrs = (
    Meta(name="viewport", content="width=device-width, initial-scale=1.0"),
    Link(rel="stylesheet", href="static/output.css", type="text/css"),
    MarkdownJS(),
    Script("""
        document.addEventListener('DOMContentLoaded', function() {
            const uploadForm = document.getElementById('upload-form');
            const fileInput = document.getElementById('file-upload');

            if (uploadForm) {
                uploadForm.addEventListener('submit', function(e) {
                    const file = fileInput.files[0];
                    if (file) {
                        // Create and show the processing overlay
                        const overlay = document.createElement('div');
                        overlay.className = 'processing-overlay fade-in';
                        overlay.id = 'processing-overlay';

                        overlay.innerHTML = `
                            <div class="processing-card">
                                <div class="spinner mb-4"></div>
                                <h3 class="text-xl font-bold text-gray-800 mb-2">Processing your PDF</h3>
                                <p class="text-gray-600 mb-4">Please wait while we analyze and index your document...</p>
                                <div class="progress-bar">
                                    <div class="progress-bar-value" id="progress-value"></div>
                                </div>
                                <div class="mt-4 text-blue-600 flex justify-center">
                                    <div class="wave mx-1">●</div>
                                    <div class="wave mx-1" style="animation-delay: 0.2s">●</div>
                                    <div class="wave mx-1" style="animation-delay: 0.4s">●</div>
                                </div>
                            </div>
                        `;

                        document.body.appendChild(overlay);

                        // Animate progress bar
                        setTimeout(() => {
                            const progressValue = document.getElementById('progress-value');
                            if (progressValue) {
                                progressValue.style.width = '100%';
                            }
                        }, 100);
                    }
                });
            }

            // Show filename when file is selected
            if (fileInput) {
                fileInput.addEventListener('change', function() {
                    const fileNameDisplay = document.getElementById('file-name-display');
                    if (fileNameDisplay && this.files.length > 0) {
                        fileNameDisplay.textContent = this.files[0].name;
                        fileNameDisplay.classList.remove('hidden');
                    }
                });
            }

            // Setup for any chat forms loaded initially
            setupChatForm();
        });

        // Function to remove the processing overlay (called by HTMX after the response)
        function removeProcessingOverlay() {
            const overlay = document.getElementById('processing-overlay');
            if (overlay) {
                overlay.classList.add('fade-out');
                setTimeout(() => {
                    overlay.remove();
                }, 500);
            }
        }

        // Scroll to bottom of chat when new message is added
        function scrollToBottom() {
            const chatContainer = document.getElementById('responses');
            if (chatContainer) {
                chatContainer.scrollTop = chatContainer.scrollHeight;
            }
        }

        // Function to fully reset everything
        function clearChat() {
            // Add fade out animation to the entire chat container
            const chatContainer = document.getElementById('chat-container');
            if (chatContainer) {
                chatContainer.classList.add('fade-out');

                // After animation completes, replace with upload form
                setTimeout(() => {
                    // Get upload form HTML from server
                    fetch('/reset', {
                        method: 'GET',
                    })
                    .then(response => response.text())
                    .then(html => {
                        chatContainer.innerHTML = html;
                        chatContainer.classList.remove('fade-out');
                        chatContainer.classList.add('fade-in');

                        // Re-initialize event listeners for the new upload form
                        const uploadForm = document.getElementById('upload-form');
                        const fileInput = document.getElementById('file-upload');

                        if (uploadForm) {
                            uploadForm.addEventListener('submit', function(e) {
                                const file = fileInput.files[0];
                                if (file) {
                                    // Create and show the processing overlay
                                    const overlay = document.createElement('div');
                                    overlay.className = 'processing-overlay fade-in';
                                    overlay.id = 'processing-overlay';

                                    overlay.innerHTML = `
                                        <div class="processing-card">
                                            <div class="spinner mb-4"></div>
                                            <h3 class="text-xl font-bold text-gray-800 mb-2">Processing your PDF</h3>
                                            <p class="text-gray-600 mb-4">Please wait while we analyze and index your document...</p>
                                            <div class="progress-bar">
                                                <div class="progress-bar-value" id="progress-value"></div>
                                            </div>
                                            <div class="mt-4 text-blue-600 flex justify-center">
                                                <div class="wave mx-1">●</div>
                                                <div class="wave mx-1" style="animation-delay: 0.2s">●</div>
                                                <div class="wave mx-1" style="animation-delay: 0.4s">●</div>
                                            </div>
                                        </div>
                                    `;

                                    document.body.appendChild(overlay);

                                    // Animate progress bar
                                    setTimeout(() => {
                                        const progressValue = document.getElementById('progress-value');
                                        if (progressValue) {
                                            progressValue.style.width = '100%';
                                        }
                                    }, 100);
                                }
                            });
                        }

                        // Show filename when file is selected
                        if (fileInput) {
                            fileInput.addEventListener('change', function() {
                                const fileNameDisplay = document.getElementById('file-name-display');
                                if (fileNameDisplay && this.files.length > 0) {
                                    fileNameDisplay.textContent = this.files[0].name;
                                    fileNameDisplay.classList.remove('hidden');
                                }
                            });
                        }
                    })
                    .catch(error => {
                        console.error('Error:', error);
                        // Fallback: Just show a message to refresh the page
                        chatContainer.innerHTML = `
                            <div class="p-5 text-center">
                                <p class="mb-4 text-white">Chat has been reset.</p>
                                <button onclick="window.location.reload()" class="px-4 py-2 bg-blue-600 text-white rounded-lg">
                                    Refresh Page
                                </button>
                            </div>
                        `;
                        chatContainer.classList.remove('fade-out');
                    });
                }, 300);
            }
        }

        // Function to add user message to chat immediately
        function addUserMessage(text) {
            const chatContainer = document.getElementById('responses');
            if (!chatContainer || !text) {
                console.log("Cannot add user message - container not found or text is empty");
                return;
            }
        
            // Remove empty state if present
            const emptyState = chatContainer.querySelector('.flex.flex-col.items-center.justify-center');
            if (emptyState) {
                emptyState.remove();
            }
            
            // Generate unique ID for message
            const messageId = 'user-message-' + Date.now();
        
            // Create user message HTML
            const userMessageHtml = `
                <div class="flex items-start mb-6 fade-in" id="${messageId}">
                    <div class="flex-shrink-0 w-8 h-8 rounded-full user-avatar flex items-center justify-center text-white mr-3">
                        <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z"></path>
                        </svg>
                    </div>
                    <div class="flex-1">
                        <div class="mb-1 text-xs text-gray-500">You</div>
                        <div class="chat-bubble-user p-3 inline-block max-w-[85%]">
                            <p class="text-gray-800">${text}</p>
                        </div>
                    </div>
                </div>
            `;
        
            // Add user message to chat
            chatContainer.insertAdjacentHTML('beforeend', userMessageHtml);
        
            // Only add thinking message if it doesn't already exist
            if (!document.getElementById('ai-thinking')) {
                const thinkingMessageHtml = `
                    <div class="flex items-start mb-6 fade-in" id="ai-thinking">
                        <div class="flex-shrink-0 w-8 h-8 rounded-full ai-avatar flex items-center justify-center text-white mr-3">
                            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
                                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z"></path>
                            </svg>
                        </div>
                        <div class="flex-1">
                            <div class="mb-1 text-xs text-gray-500">AI</div>
                            <div class="chat-bubble-ai p-3 inline-block max-w-[85%]">
                                <div class="flex items-center space-x-2">
                                    <span class="inline-block pulse text-blue-500">⚫</span>
                                    <span class="inline-block pulse text-blue-500" style="animation-delay: 0.2s">⚫</span>
                                    <span class="inline-block pulse text-blue-500" style="animation-delay: 0.4s">⚫</span>
                                    <span class="ml-2 text-gray-600">Thinking...</span>
                                </div>
                            </div>
                        </div>
                    </div>
                `;
        
                chatContainer.insertAdjacentHTML('beforeend', thinkingMessageHtml);
            }
        
            // Scroll to bottom
            scrollToBottom();
        
            return messageId;
        }


        
        // Setup function for chat form submission with animation
        function setupChatForm() {
            const chatForm = document.querySelector('form[hx-post="/ask"]');
            const chatInput = document.querySelector('input[name="query"]');
        
            if (chatForm && chatInput) {
                // Remove HTMX attributes to prevent double processing
                chatForm.removeAttribute('hx-post');
                chatForm.removeAttribute('hx-target');
                chatForm.removeAttribute('hx-swap');
                
                // Remove any existing event listeners
                chatForm.removeEventListener('submit', handleChatSubmit);
        
                // Add event listener for form submission
                chatForm.addEventListener('submit', handleChatSubmit);
        
                // Add event listener for Enter key
                chatInput.addEventListener('keydown', function(e) {
                    if (e.key === 'Enter' && !e.shiftKey) {
                        e.preventDefault();
                        const submitEvent = new Event('submit', { cancelable: true });
                        chatForm.dispatchEvent(submitEvent);
                    }
                });
            }
        
            // Setup clear button
            const clearButton = document.getElementById('clear-chat-button');
            if (clearButton) {
                clearButton.addEventListener('click', clearChat);
            }
        }

        // Handle chat form submission
        // Handle chat form submission
        // This is the improved handleChatSubmit function that should correctly process responses
        function handleChatSubmit(e) {
            e.preventDefault(); // Prevent the default form submission
            
            const form = e.currentTarget;
            const chatInput = form.querySelector('input[name="query"]');
            const query = chatInput.value.trim();
            console.log("Form submission - Query:", query);
        
            if (!query) {
                console.log("Empty query, preventing form submission");
                return;
            }
        
            // Add user message immediately
            addUserMessage(query);
            
            // Clear input
            chatInput.value = '';
            
            // Get the filename
            const filenameInput = form.querySelector('input[name="filename"]');
            const filename = filenameInput.value;
            
            // Make our own fetch request
            const formData = new FormData();
            formData.append('query', query);
            formData.append('filename', filename);
            
            fetch('/ask', {
                method: 'POST',
                body: formData
            })
            .then(response => {
                console.log("Response status:", response.status);
                return response.text();
            })
            .then(html => {
                console.log("Received HTML response:", html.substring(0, 100) + "...");
                
                // Remove thinking message
                const thinking = document.getElementById('ai-thinking');
                if (thinking) thinking.remove();
                
                // Append the response HTML directly to the chat container
                const chatContainer = document.getElementById('responses');
                
                try {
                    // Direct insertion of HTML
                    chatContainer.insertAdjacentHTML('beforeend', html);
                    console.log("Response added to chat");
                } catch (err) {
                    console.error("Error inserting response:", err);
                    chatContainer.insertAdjacentHTML('beforeend', `
                        <div class="flex items-start mb-6 fade-in">
                            <div class="flex-shrink-0 w-8 h-8 rounded-full ai-avatar flex items-center justify-center text-white mr-3">
                                <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
                                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z"></path>
                                </svg>
                            </div>
                            <div class="flex-1">
                                <div class="mb-1 text-xs text-gray-500">AI</div>
                                <div class="chat-bubble-ai p-3 inline-block max-w-[85%]">
                                    <p class="text-gray-800">I encountered an error displaying the response.</p>
                                </div>
                            </div>
                        </div>
                    `);
                }
                
                // Scroll to bottom
                scrollToBottom();
            })
            .catch(error => {
                console.error('Error:', error);
                
                // Remove thinking message and show error
                const thinking = document.getElementById('ai-thinking');
                if (thinking) {
                    thinking.outerHTML = `
                        <div class="flex items-start mb-6 fade-in">
                            <div class="flex-shrink-0 w-8 h-8 rounded-full bg-red-500 flex items-center justify-center text-white mr-3">
                                <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
                                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"></path>
                                </svg>
                            </div>
                            <div class="flex-1">
                                <div class="mb-1 text-xs text-gray-500">Error</div>
                                <div class="chat-bubble-user bg-red-50 p-3 inline-block max-w-[85%] border border-red-200">
                                    <p class="text-red-700">An error occurred while processing your request.</p>
                                </div>
                            </div>
                        </div>
                    `;
                    scrollToBottom();
                }
            });
        }


        // Update these event listeners
        document.addEventListener('htmx:afterOnLoad', function(event) {
            removeProcessingOverlay();
            scrollToBottom();
            setupChatForm();
        });
        
        document.addEventListener('htmx:afterSettle', function(event) {
            setupChatForm();
        });
        
        document.addEventListener('DOMContentLoaded', function() {
            setupChatForm();
        });
    """)
)

# Set up route for static files
app, rt = fast_app(hdrs=hdrs, pico=False, live=False)


@rt("/")
def get():
    return Main(
        Title("Document Retriever"),
        Div(cls="mt-16 flex flex-col justify-center")(
            Div(cls="max-w-4xl mx-auto")(
                # Header
                Div(cls="text-center mb-16")(
                    H1(cls="text-5xl font-extrabold tracking-tight text-white sm:text-6xl")(
                        "Document Retriever",
                        Span(cls="relative whitespace-nowrap")(
                            Svg(cls="absolute top-2/3 left-0 h-[0.58em] w-full fill-white/30",
                                aria_hidden="true",
                                viewBox="0 0 418 42", preserveAspectRatio="none")(
                                Path(
                                    d="M203.371.916c-26.013-2.078-76.686 1.963-124.73 9.946L67.3 12.749C35.421 18.062 18.2 21.766 6.004 25.934 1.244 27.561.828 27.778.874 28.61c.07 1.214.828 1.121 9.595-1.176 9.072-2.377 17.15-3.92 39.246-7.496C123.565 7.986 157.869 4.492 195.942 5.046c7.461.108 19.25 1.696 19.17 2.582-.107 1.183-7.874 4.31-25.75 10.366-21.992 7.45-35.43 12.534-36.701 13.884-2.173 2.308-.202 4.407 4.442 4.734 2.654.187 3.263.157 15.593-.78 35.401-2.686 57.944-3.488 88.365-3.143 46.327.526 75.721 2.23 130.788 7.584 19.787 1.924 20.814 1.98 24.557 1.332l.066-.011c1.201-.203 1.53-1.825.399-2.335-2.911-1.31-4.893-1.604-22.048-3.261-57.509-5.556-87.871-7.36-132.059-7.842-23.239-.254-33.617-.116-50.627.674-11.629.54-42.371 2.494-46.696 2.967-2.359.259 8.133-3.625 26.504-9.81 23.239-7.825 27.934-10.149 28.304-14.005.417-4.348-3.529-6-16.878-7.066Z")
                            ),

                        ),
                    ),
                    P(cls="mt-6 text-xl text-blue-100 max-w-2xl mx-auto")(
                        "Upload a PDF document and ask questions about it."
                    ),
                ),

                # Upload form with glass effect
                Div(id="chat-container")(
                    render_upload_form()
                )
            )
        )
    )


def render_upload_form():
    return Form(id="upload-form", cls="mt-8 max-w-xl mx-auto", method="post", action="/upload",
                enctype="multipart/form-data",
                hx_post="/upload", hx_target="#chat-container", hx_swap="innerHTML")(
        Div(cls="flex flex-col items-center justify-center w-full")(
            Label(
                cls="flex flex-col items-center justify-center w-full h-64 glass-card upload-zone rounded-xl cursor-pointer transition-all shadow-lg",
                htmlFor="file-upload")(
                Div(cls="flex flex-col items-center justify-center pt-5 pb-6")(
                    Svg(cls="w-16 h-16 mb-4 text-blue-600", fill="none", stroke="currentColor",
                        viewBox="0 0 24 24", xmlns="http://www.w3.org/2000/svg")(
                        Path(stroke_linecap="round", stroke_linejoin="round", stroke_width="2",
                             d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12")
                    ),
                    P(cls="mb-2 text-lg text-blue-700")(Span(cls="font-semibold")("Click to upload"),
                                                        " or drag and drop"),
                    P(cls="text-sm text-blue-500")("PDF files only (Max 10MB)"),
                    P(id="file-name-display", cls="mt-2 text-sm font-medium text-blue-700 hidden")("")
                ),
                Input(id="file-upload", type="file", cls="hidden", name="file", accept=".pdf")
            ),
            Button(
                cls="mt-6 inline-flex items-center justify-center rounded-lg py-3 px-6 text-base font-medium text-white bg-blue-600 hover:bg-blue-700 focus:ring-4 focus:ring-blue-300 focus:outline-none btn-primary transition-all shadow-lg",
                type="submit")(
                "Upload PDF"
            )
        )
    )


@rt("/reset")
def get():
    # Return just the upload form HTML
    return render_upload_form()


@rt("/upload")
async def post(request):
    form = await request.form()
    file = form.get("file")

    if file is None or file.filename == "":
        return Div(cls="p-4 mb-4 text-sm text-red-700 bg-red-100 rounded-lg border border-red-200 glass-card",
                   role="alert")(
            Svg(cls="w-5 h-5 inline mr-2 flex-shrink-0", fill="currentColor", viewBox="0 0 20 20",
                xmlns="http://www.w3.org/2000/svg")(
                Path(fill_rule="evenodd",
                     d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7-4a1 1 0 11-2 0 1 1 0 012 0zM9 9a1 1 0 000 2v3a1 1 0 001 1h1a1 1 0 100-2v-3a1 1 0 00-1-1H9z",
                     clip_rule="evenodd")
            ),
            "No file was uploaded."
        )

    if not file.filename.lower().endswith('.pdf'):
        return Div(cls="p-4 mb-4 text-sm text-red-700 bg-red-100 rounded-lg border border-red-200 glass-card",
                   role="alert")(
            Svg(cls="w-5 h-5 inline mr-2 flex-shrink-0", fill="currentColor", viewBox="0 0 20 20",
                xmlns="http://www.w3.org/2000/svg")(
                Path(fill_rule="evenodd",
                     d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7-4a1 1 0 11-2 0 1 1 0 012 0zM9 9a1 1 0 000 2v3a1 1 0 001 1h1a1 1 0 100-2v-3a1 1 0 00-1-1H9z",
                     clip_rule="evenodd")
            ),
            "Please upload a PDF file."
        )

    # Create a unique filename
    filename = f"{uuid.uuid4()}.pdf"
    file_path = uploads_dir / filename

    # Save the uploaded file
    with open(file_path, "wb") as f:
        f.write(await file.read())

    # Index the PDF with the RAG model
    try:
        RAG.index(
            input_path=str(file_path),
            index_name=filename,
            store_collection_with_index=True,
            overwrite=True
        )

        # Return chat interface with glass effect design - updated to match the reference image
        return Div(
            # Success animation notification
            Div(cls="p-5 mb-6 text-green-700 glass-card rounded-lg border border-green-200 shadow-lg fade-in",
                role="alert")(
                Div(cls="flex items-center")(
                    Div(cls="flex-shrink-0")(
                        Svg(cls="w-8 h-8 text-green-500", fill="none", stroke="currentColor", viewBox="0 0 24 24",
                            xmlns="http://www.w3.org/2000/svg")(
                            Path(stroke_linecap="round", stroke_linejoin="round", stroke_width="2",
                                 d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z")
                        )
                    ),
                    Div(cls="ml-4")(
                        H3(cls="text-lg font-medium text-green-800")("PDF Successfully Processed"),
                        Div(cls="mt-1 text-sm text-green-700")(
                            f"Your file '{file.filename}' has been uploaded and indexed successfully. You can now ask questions about its content."
                        )
                    )
                )
            ),

            # Glass-like chat interface matching the reference image
            Div(cls="glass-chat shadow-xl overflow-hidden border border-white/30 w-full")(
                # Chat header with file info
                Div(cls="chat-header p-4 flex items-center justify-between")(
                    # Left side with file info
                    Div(cls="flex items-center")(
                        Div(cls="w-10 h-10 rounded-full bg-blue-500/40 flex items-center justify-center text-white mr-3")(
                            Svg(cls="w-6 h-6", fill="none", stroke="currentColor", viewBox="0 0 24 24",
                                xmlns="http://www.w3.org/2000/svg")(
                                Path(stroke_linecap="round", stroke_linejoin="round", stroke_width="2",
                                     d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z")
                            )
                        ),
                        Div(
                            H3(cls="text-lg font-medium text-white")(file.filename),
                            P(cls="text-sm text-blue-100")("Ask questions about this document")
                        )
                    ),

                    # Right side with clear button
                    Button(id="clear-chat-button", type="button",
                           cls="clear-button flex-shrink-0", title="Clear conversation")(
                        Div(cls="flex items-center")(
                            "Clear"
                        )
                    )
                ),

                # Messages container with empty state
                Div(id="responses",
                    cls="chat-container p-4 h-[400px] overflow-y-auto")(
                    Div(cls="h-full flex flex-col items-center justify-center text-center py-10 text-gray-500")(
                        Svg(cls="w-16 h-16 mb-4 text-blue-300", fill="none", stroke="currentColor", viewBox="0 0 24 24",
                            xmlns="http://www.w3.org/2000/svg")(
                            Path(stroke_linecap="round", stroke_linejoin="round", stroke_width="2",
                                 d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z")
                        ),
                        P(cls="text-xl font-medium text-gray-600 mb-2")("No questions yet"),
                        P(cls="text-gray-500 max-w-md")(
                            "Start by asking a question about your document in the input box below.")
                    )
                ),

                # Input area with rounded input and send button with text
                Form(cls="chat-footer p-4 flex items-center gap-2", method="post",
                     action="/ask",
                     hx_post="/ask", hx_target="#responses", hx_swap="beforeend")(
                    Input(type="hidden", name="filename", value=filename),
                    Div(cls="relative flex-1")(
                        Input(
                            cls="chat-input w-full text-slate-800 placeholder-slate-400 focus:outline-none pr-10",
                            type="text", name="query", placeholder="Ask a question about the document...",
                            autocomplete="off"),
                    ),
                    Button(
                        cls="send-button flex-shrink-0",
                        type="submit")(
                        Div(cls="flex items-center")(
                            "Send"
                        )
                    )
                )
            ),

            # Add JavaScript to remove the processing overlay and scroll to bottom
            Script("removeProcessingOverlay(); scrollToBottom(); setupChatForm();")
        )
    except Exception as e:
        return Div(
            Script("removeProcessingOverlay();"),
            Div(cls="p-4 mb-4 text-sm text-red-700 bg-red-100 rounded-lg border border-red-200 glass-card",
                role="alert")(
                Svg(cls="w-5 h-5 inline mr-2 flex-shrink-0", fill="currentColor", viewBox="0 0 20 20",
                    xmlns="http://www.w3.org/2000/svg")(
                    Path(fill_rule="evenodd",
                         d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7-4a1 1 0 11-2 0 1 1 0 012 0zM9 9a1 1 0 000 2v3a1 1 0 001 1h1a1 1 0 100-2v-3a1 1 0 00-1-1H9z",
                         clip_rule="evenodd")
                ),
                f"Error indexing the PDF: {str(e)}"
            )
        )


@rt("/ask")
async def post(request):
    # Get form data
    form_data = await request.form()
    query = form_data.get("query", "")
    filename = form_data.get("filename", "")

    if not query or not filename:
        print(f"Missing query or filename. Query: '{query}', Filename: '{filename}'")
        return Div(cls="flex items-start mb-6 fade-in")(
            Div(cls="flex-shrink-0 w-8 h-8 rounded-full ai-avatar flex items-center justify-center text-white mr-3")(
                Svg(cls="w-4 h-4", fill="none", stroke="currentColor", viewBox="0 0 24 24",
                    xmlns="http://www.w3.org/2000/svg")(
                    Path(stroke_linecap="round", stroke_linejoin="round", stroke_width="2",
                         d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z")
                )
            ),
            Div(cls="flex-1")(
                Div(cls="mb-1 text-xs text-gray-500")("Claude"),
                Div(cls="chat-bubble-ai p-3 inline-block max-w-[85%]")(
                    P(cls="text-gray-800")(
                        "I'm having trouble processing your request. Could you try asking another question?")
                )
            )
        )

    try:
        # Search the RAG model
        print(f"Searching RAG model for query: {query}")
        results = RAG.search(query, k=1)

        if not results:
            print("No search results found")
            return Div(cls="flex items-start mb-6 fade-in")(
                Div(cls="flex-shrink-0 w-8 h-8 rounded-full ai-avatar flex items-center justify-center text-white mr-3")(
                    Svg(cls="w-4 h-4", fill="none", stroke="currentColor", viewBox="0 0 24 24",
                        xmlns="http://www.w3.org/2000/svg")(
                        Path(stroke_linecap="round", stroke_linejoin="round", stroke_width="2",
                             d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z")
                    )
                ),
                Div(cls="flex-1")(
                    Div(cls="mb-1 text-xs text-gray-500")("Claude"),
                    Div(cls="chat-bubble-ai p-3 inline-block max-w-[85%]")(
                        P(cls="text-gray-800")(
                            "I couldn't find any relevant information in the document to answer your question. Could you try rephrasing it?")
                    )
                )
            )

        # Get the image from the search results and resize it to fit within Claude's limits
        print("Decoding image from search results")
        image_bytes = base64.b64decode(results[0].base64)
        original_size = len(image_bytes) / (1024 * 1024)
        print(f"Original image size: {original_size:.2f} MB")

        # Always resize the image to ensure it's well under the limit
        try:
            image_bytes = resize_image_for_claude(image_bytes)
            final_size = len(image_bytes) / (1024 * 1024)
            print(f"Resized image size: {final_size:.2f} MB")

            # Double-check size is within limits
            if len(image_bytes) > 5 * 1024 * 1024:
                raise ValueError(f"Image still too large after resizing: {final_size:.2f} MB")

        except Exception as resize_error:
            print(f"Error resizing image: {resize_error}")
            return Div(cls="flex items-start mb-6 fade-in")(
                Div(cls="flex-shrink-0 w-8 h-8 rounded-full ai-avatar flex items-center justify-center text-white mr-3")(
                    Svg(cls="w-4 h-4", fill="none", stroke="currentColor", viewBox="0 0 24 24",
                        xmlns="http://www.w3.org/2000/svg")(
                        Path(stroke_linecap="round", stroke_linejoin="round", stroke_width="2",
                             d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z")
                    )
                ),
                Div(cls="flex-1")(
                    Div(cls="mb-1 text-xs text-gray-500")("AI"),
                    Div(cls="chat-bubble-ai p-3 inline-block max-w-[85%]")(
                        P(cls="text-gray-800")(
                            f"I had trouble processing the image from your document ({original_size:.1f}MB). The PDF page may be too complex or large. Try asking about a specific section instead.")
                    )
                )
            )

        # Ask Claude
        print("Sending query to Claude")
        chat = Chat(models[1])  # Using Claude Sonnet
        result = chat([image_bytes, query])
        print("Received response from Claude")
        ai_text = result.content[0].text if result.content else "Sorry, I couldn't generate a response."

        # Return just Claude's response - the user message is already added by JavaScript
        return Div(cls="flex items-start mb-6 fade-in")(
            Div(cls="flex-shrink-0 w-8 h-8 rounded-full ai-avatar flex items-center justify-center text-white mr-3")(
                Svg(cls="w-4 h-4", fill="none", stroke="currentColor", viewBox="0 0 24 24",
                    xmlns="http://www.w3.org/2000/svg")(
                    Path(stroke_linecap="round", stroke_linejoin="round", stroke_width="2",
                         d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z")
                )
            ),
            Div(cls="flex-1")(
                Div(cls="mb-1 text-xs text-gray-500")("Claude"),
                Div(cls="chat-bubble-ai p-3 inline-block max-w-[85%]")(
                    Div(cls="text-gray-800 prose prose-sm max-w-none marked")(ai_text)
                )
            )
        )
    except Exception as e:
        error_message = str(e)
        print(f"Error in /ask: {error_message}")

        # More user-friendly error message
        if "image exceeds 5 MB maximum" in error_message:
            friendly_message = "The PDF page is too large for Claude to process. Try asking about a specific section of the document or a different page."
        else:
            friendly_message = "I encountered an issue while processing your question. Please try again or ask a different question."

        print(f"Returning error message to user: {friendly_message}")

        return Div(cls="flex items-start mb-6 fade-in")(
            Div(cls="flex-shrink-0 w-8 h-8 rounded-full bg-red-500 flex items-center justify-center text-white mr-3")(
                Svg(cls="w-4 h-4", fill="none", stroke="currentColor", viewBox="0 0 24 24",
                    xmlns="http://www.w3.org/2000/svg")(
                    Path(stroke_linecap="round", stroke_linejoin="round", stroke_width="2",
                         d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z")
                )
            ),
            Div(cls="flex-1")(
                Div(cls="mb-1 text-xs text-gray-500")("Error"),
                Div(cls="chat-bubble-user bg-red-50 p-3 inline-block max-w-[85%] border border-red-200")(
                    P(cls="text-red-700")(friendly_message)
                )
            )
        )


# Run the app
serve()