import os
import shutil
from pathlib import Path
import PyPDF2
import requests
import json
import logging
from typing import Dict, List, Tuple

class BibliographyOrganizer:
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.api_url = "https://openrouter.ai/api/v1/chat/completions"
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        # Set up logging
        logging.basicConfig(
            filename='bibliography_organizer.log',
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        self.logger = logging.getLogger(__name__)
        self.metadata_cache = {}
        self._build_metadata_cache()

    def _build_metadata_cache(self):
        """Parse the log file to build a cache of processed filenames and their metadata."""
        log_file = 'bibliography_organizer.log'
        if not os.path.exists(log_file):
            return

        encodings = ['utf-8', 'latin-1', 'cp1252']
        for encoding in encodings:
            try:
                with open(log_file, 'r', encoding=encoding) as f:
                    lines = f.readlines()
                break
            except UnicodeDecodeError:
                if encoding == encodings[-1]:
                    self.logger.error(f"Failed to read log file with encodings: {encodings}")
                    return
                continue

        current_file = None
        for i in range(len(lines)):
            line = lines[i].rstrip('\n')
            if line.startswith('20'):
                parts = line.split(' - ', 3)
                if len(parts) < 3:
                    continue
                message = parts[2]
                if "Processing file: " in message:
                    current_file = message.split("Processing file: ")[1].strip()
                elif "Model output:" in message and current_file is not None:
                    # Collect JSON lines
                    json_lines = []
                    j = i + 1
                    while j < len(lines) and not lines[j].startswith('20'):
                        json_lines.append(lines[j].rstrip('\n'))
                        j += 1
                    json_str = '\n'.join(json_lines)
                    try:
                        data = json.loads(json_str)
                        title = data.get('title', '')
                        author = data.get('author', '')
                        # Store in cache even if empty to avoid reprocessing
                        self.metadata_cache[current_file] = (title, author)
                    except json.JSONDecodeError:
                        pass
                    current_file = None  # Reset after processing

    def query_deepseek(self, prompt: str) -> str:
        try:
            self.logger.info("=== Starting API Query ===")
            self.logger.info(f"Prompt sent to model:\n{prompt}")
            
            payload = {
                "model": "deepseek/deepseek-r1-distill-llama-70b:free",
                "messages": [{"role": "user", "content": prompt}]
            }
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://bibliography-organizer.local",
                "X-Title": "Bibliography Organizer"
            }
            
            response = requests.post(
                self.api_url,
                headers=headers,
                json=payload,
                timeout=(15, 30)
            )
            response.raise_for_status()
            
            try:
                response_json = response.json()
                
                if "error" in response_json:
                    error_msg = response_json["error"].get("message", "Unknown error")
                    self.logger.error(f"API Error: {error_msg}")
                    return ""
                
                if "choices" not in response_json or not response_json["choices"]:
                    self.logger.error("Response format error: 'choices' field missing or empty")
                    raise ValueError("Response does not contain 'choices'")
                
                result = response_json['choices'][0]['message']['content']
                
                # Clean up markdown code block formatting and extract JSON
                result = result.strip()
                
                # Enhanced JSON extraction
                try:
                    # Remove Python tags and headers if present
                    result = result.replace('<|python_tag|>', '')
                    result = result.replace('<|start_header_id|>assistant<|end_header_id|>', '')
                    
                    # Find all potential JSON objects in the text
                    potential_jsons = []
                    start = 0
                    while True:
                        try:
                            # Find the next JSON-like structure
                            start = result.find('{', start)
                            if start == -1:
                                break
                            
                            # Track nested braces
                            brace_count = 1
                            pos = start + 1
                            
                            while brace_count > 0 and pos < len(result):
                                if result[pos] == '{':
                                    brace_count += 1
                                elif result[pos] == '}':
                                    brace_count -= 1
                                pos += 1
                            
                            if brace_count == 0:
                                potential_json = result[start:pos]
                                try:
                                    # Validate if it's valid JSON
                                    json.loads(potential_json)
                                    potential_jsons.append(potential_json)
                                except json.JSONDecodeError:
                                    pass
                            
                            start = pos
                        except ValueError:
                            break
                    
                    # Use the longest valid JSON found (usually the most complete)
                    if potential_jsons:
                        result = max(potential_jsons, key=len)
                    
                except (ValueError, json.JSONDecodeError):
                    # If we can't find valid JSON this way, try the original string
                    pass
                
                # Remove any markdown formatting if present
                if result.startswith('```'):
                    first_newline = result.find('\n')
                    if first_newline != -1:
                        result = result[first_newline + 1:]
                    if result.endswith('```'):
                        result = result[:-3]
                result = result.strip()
                
                self.logger.info(f"Model output:\n{result}")
                return result
                
            except json.JSONDecodeError:
                self.logger.error(f"Failed to parse API response as JSON:\n{response.text}")
                return ""
                
        except requests.exceptions.RequestException as e:
            self.logger.error(f"API Request failed: {str(e)}")
            return ""
        except Exception as e:
            self.logger.error(f"Unexpected error in query_deepseek: {str(e)}")
            self.logger.exception("Full error traceback:")
            return ""

    def sanitize_filename(self, filename: str) -> str:
        # Remove special characters and convert spaces to underscores
        sanitized = filename.replace(' ', '_')
        # Keep only alphanumeric characters, dots, underscores and hyphens
        sanitized = ''.join(c for c in sanitized if c.isalnum() or c in '._-')
        return sanitized

    def extract_document_info(self, file_path: str) -> Tuple[str, str]:
        self.logger.info(f"Extracting document info from: {file_path}")
        filename = Path(file_path).name
        sanitized_filename = self.sanitize_filename(filename)

        # Check cache first
        if filename in self.metadata_cache:
            title, author = self.metadata_cache[filename]
            if title and author:
                self.logger.info(f"Using cached metadata - Title: {title}, Authors: {author}")
                return title, author
            else:
                self.logger.info(f"Cached metadata not found for {filename}")
                return '', ''

        # Proceed with API query if not in cache
        prompt = f"I will give you a filename of a file which is an academic work. I want you to use the data in the filename to look in the web for the full title of the academic work and its author's surname. Also, find out if it is an article or a book. I want you to return ONLY a JSON object with the title (the key will be named title) and author's surname (the key will be named author) obtained, and also with the document type (article or book, the key will be named document_type). The response must contain ONLY the JSON, no other text. Do not give me responses with code blocks! Use empty strings if you can't determine both values clearly. {sanitized_filename}"
        response = self.query_deepseek(prompt)
        try:
            info = json.loads(response)
            title = info.get('title', '')
            author = info.get('author', '')
            # Update cache even if empty
            self.metadata_cache[filename] = (title, author)
            if title and author:
                self.logger.info(f"Successfully extracted document info - Title: {title}, Authors: {author}")
                return title, author
            else:
                self.logger.warning(f"Could not extract title and authors from filename: {filename}")
                return '', ''
        except:
            self.logger.error(f"Failed to parse filename info response for: {file_path}")
            return '', ''

    def organize_files(self, input_folder: str):
        print("\n=== Starting Bibliography Organization Process ===")
        self.logger.info(f"Starting file organization in folder: {input_folder}")
        documents_info = {}

        # Process each file
        pdf_files = [f for f in Path(input_folder).glob('*.pdf')]
        total_files = len(pdf_files)
        print(f"\nFound {total_files} PDF files to process")

        for idx, file_path in enumerate(pdf_files, 1):
            print(f"\nProcessing file {idx}/{total_files}: {file_path.name}")
            self.logger.info(f"Processing file: {file_path.name}")
            title, author = self.extract_document_info(str(file_path))
            if title and author:
                print(f"  ✓ Extracted metadata - Title: {title}, Authors: {author}")
                documents_info[str(file_path)] = {
                    'title': title,
                    'author': author,
                    'file_type': 'Book'
                }
            else:
                print("  ✗ Could not extract title/authors from filename")
                self.logger.warning(f"Skipping file due to missing title/authors: {file_path.name}")

        if not documents_info:
            print("\n✗ No valid documents to process. Stopping organization.")
            self.logger.error("No documents with valid metadata found. Stopping organization process.")
            return

        print("\n=== Creating Organization Plan ===")
        works_list = [f"{info['title']} by {info['author']}" for info in documents_info.values()]
        works_text = '\n'.join(works_list)
        
        prompt = f"""I will give you a list of academic works. Based on it, create a simple organization scheme that best fits these works.

Return ONLY a JSON object with a single property 'placements' that maps each work title to its designated folder path. The folder paths should use forward slashes and can be nested (e.g. 'Science/Physics').

Works to organize:\n{works_text}"""

        response = self.query_deepseek(prompt)
        
        try:
            organization_plan = json.loads(response)
            if not isinstance(organization_plan, dict) or 'placements' not in organization_plan:
                print("✗ Failed to generate valid organization plan. Stopping organization.")
                self.logger.error("Invalid organization plan format received")
                return

            print("\n=== Creating Folder Structure ===")
            folder_paths = {}
            
            # Extract unique folder paths from placements
            unique_folders = set(organization_plan['placements'].values())
            
            # Create folders with support for nested structure
            for folder_path in unique_folders:
                folder_path_parts = folder_path.split('/')
                current_path = Path(input_folder)
                
                # Create each level of the folder structure
                for part in folder_path_parts:
                    part = self.sanitize_filename(part)
                    current_path = current_path / part
                    try:
                        current_path.mkdir(exist_ok=True)
                        folder_paths[folder_path] = current_path
                        print(f"  ✓ Created folder: {folder_path}")
                        self.logger.info(f"Created folder: {current_path}")
                    except Exception as e:
                        print(f"  ✗ Error creating folder {part}: {str(e)}")
                        self.logger.error(f"Error creating folder {current_path}: {str(e)}")

            if not folder_paths:
                print("✗ Failed to create any folders. Stopping organization.")
                self.logger.error("No folders were created")
                return

            print("\n=== Organizing Files ===")
            organized_count = 0

            for file_path, info in documents_info.items():
                file_path = Path(file_path)
                work_key = f"{info['title']} by {info['author']}"
                
                # Find the target folder for this work
                target_folder_path = organization_plan['placements'].get(work_key)
                
                if target_folder_path and target_folder_path in folder_paths:
                    new_filename = f"{info['author'].split(',')[0]}-{info['title']}"
                    new_filename = self.sanitize_filename(new_filename)
                    new_filename = f"{new_filename}{file_path.suffix}"

                    destination = folder_paths[target_folder_path] / new_filename
                    try:
                        shutil.move(file_path, destination)
                        print(f"  ✓ Moved '{title}' to folder: {target_folder_path}")
                        print(f"  ✓ New filename: {new_filename}")
                        organized_count += 1
                        self.logger.info(f"Successfully moved and renamed file to: {destination}")
                    except Exception as e:
                        print(f"  ✗ Error moving file: {str(e)}")
                        self.logger.error(f"Error moving file to {destination}: {str(e)}")
                else:
                    print(f"  ✗ No folder assignment found for '{info['title']}'")
                    self.logger.error(f"No matching placement found for '{info['title']}'")

            print(f"\n=== Organization Complete ===")
            print(f"Successfully organized {organized_count} out of {len(documents_info)} files")
            print("Check bibliography_organizer.log for detailed information")
            self.logger.info("Organization complete!")

        except json.JSONDecodeError:
            print("✗ Failed to parse organization plan response. Stopping organization.")
            self.logger.error("Failed to parse organization plan JSON response")
            return

        print(f"\n=== Organization Complete ===")
        print(f"Successfully organized {organized_count} out of {len(documents_info)} files")
        print("Check bibliography_organizer.log for detailed information")
        self.logger.info("Organization complete!")

    def find_last_placement_json(self) -> str:
        """Search through the log file for the most recent valid placement JSON."""
        try:
            with open('bibliography_organizer.log', 'r', encoding='utf-8') as f:
                log_content = f.read()
            
            # Find all potential JSON objects in the text
            potential_jsons = []
            start = 0
            while True:
                try:
                    # Find the next JSON-like structure
                    start = log_content.find('{', start)
                    if start == -1:
                        break
                    
                    # Track nested braces
                    brace_count = 1
                    pos = start + 1
                    
                    while brace_count > 0 and pos < len(log_content):
                        if log_content[pos] == '{':
                            brace_count += 1
                        elif log_content[pos] == '}':
                            brace_count -= 1
                        pos += 1
                    
                    if brace_count == 0:
                        potential_json = log_content[start:pos]
                        try:
                            # Validate if it's valid JSON with placements
                            parsed = json.loads(potential_json)
                            if isinstance(parsed, dict) and 'placements' in parsed:
                                potential_jsons.append(potential_json)
                        except json.JSONDecodeError:
                            pass
                    
                    start = pos
                except ValueError:
                    break
            
            # Return the last valid placement JSON found
            return potential_jsons[-1] if potential_jsons else ''
            
        except Exception as e:
            self.logger.error(f"Error searching for placement JSON in log: {str(e)}")
            return ''

    def resume_organization(self, input_folder: str, placements_json: str):
        print("\n=== Resuming Organization Process ===")
        self.logger.info("Resuming organization with provided placements JSON")

        try:
            organization_plan = json.loads(placements_json)
            if not isinstance(organization_plan, dict) or 'placements' not in organization_plan:
                print("✗ Invalid organization plan format. Stopping organization.")
                self.logger.error("Invalid organization plan format in provided JSON")
                return

            print("\n=== Creating Folder Structure ===")
            folder_paths = {}
            
            # Extract unique folder paths from placements
            unique_folders = set(organization_plan['placements'].values())
            
            # Create folders with support for nested structure
            for folder_path in unique_folders:
                folder_path_parts = folder_path.split('/')
                current_path = Path(input_folder)
                
                # Create each level of the folder structure
                for part in folder_path_parts:
                    part = self.sanitize_filename(part)
                    current_path = current_path / part
                    try:
                        current_path.mkdir(exist_ok=True)
                        folder_paths[folder_path] = current_path
                        print(f"  ✓ Created folder: {folder_path}")
                        self.logger.info(f"Created folder: {current_path}")
                    except Exception as e:
                        print(f"  ✗ Error creating folder {part}: {str(e)}")
                        self.logger.error(f"Error creating folder {current_path}: {str(e)}")

            if not folder_paths:
                print("✗ Failed to create any folders. Stopping organization.")
                self.logger.error("No folders were created")
                return

            print("\n=== Organizing Files ===")
            organized_count = 0

            # Process each PDF file in the input folder
            pdf_files = list(Path(input_folder).glob('*.pdf'))
            total_files = len(pdf_files)
            print(f"Found {total_files} PDF files to process")

            for file_path in pdf_files:
                title, author = self.extract_document_info(str(file_path))
                if not title or not author:
                    print(f"  ✗ Skipping {file_path.name} - Could not extract metadata")
                    continue

                work_key = f"{title} by {author}"
                target_folder_path = organization_plan['placements'].get(work_key)
                
                if target_folder_path and target_folder_path in folder_paths:
                    new_filename = f"{author.split(',')[0]}-{title}"
                    new_filename = self.sanitize_filename(new_filename)
                    new_filename = f"{new_filename}{file_path.suffix}"

                    destination = folder_paths[target_folder_path] / new_filename
                    try:
                        shutil.move(file_path, destination)
                        print(f"  ✓ Moved '{title}' to folder: {target_folder_path}")
                        print(f"  ✓ New filename: {new_filename}")
                        organized_count += 1
                        self.logger.info(f"Successfully moved and renamed file to: {destination}")
                    except Exception as e:
                        print(f"  ✗ Error moving file: {str(e)}")
                        self.logger.error(f"Error moving file to {destination}: {str(e)}")
                else:
                    print(f"  ✗ No folder assignment found for '{title}'")
                    self.logger.error(f"No matching placement found for '{title}'")

            print(f"\n=== Organization Complete ===")
            print(f"Successfully organized {organized_count} out of {total_files} files")
            print("Check bibliography_organizer.log for detailed information")
            self.logger.info("Organization complete!")

        except json.JSONDecodeError:
            print("✗ Failed to parse provided JSON. Stopping organization.")
            self.logger.error("Failed to parse provided placements JSON")
            return

def main():
    # Get API key from user
    api_key = input("Please enter your OpenRouter API key: ").strip()
    if not api_key:
        print("Error: API key is required!")
        logging.error("No API key provided")
        return
        
    organizer = BibliographyOrganizer(api_key)
    
    # Get input folder from user
    input_folder = input("Enter the path to the folder containing your documents: ")
    if not os.path.exists(input_folder):
        print("Invalid folder path!")
        logging.error(f"Invalid folder path provided: {input_folder}")
        return

    # Ask if user wants to resume with existing placements
    resume = input("Do you want to resume with existing placements? (yes/no): ").lower().strip()
    if resume == 'yes':
        # Try to find placement JSON in log file
        placements_json = organizer.find_last_placement_json()
        if placements_json:
            print("Found previous placement JSON in log file.")
            organizer.resume_organization(input_folder, placements_json)
        else:
            print("No valid placement JSON found in log file.")
            manual_json = input("Would you like to paste the placements JSON manually? (yes/no): ").lower().strip()
            if manual_json == 'yes':
                placements_json = input("Paste the placements JSON: ")
                organizer.resume_organization(input_folder, placements_json)
            else:
                print("Starting fresh organization...")
                organizer.organize_files(input_folder)
    else:
        organizer.organize_files(input_folder)

if __name__ == "__main__":
    main()