# 🧠 Stimulus Generator

<div align="center">

![Version](https://img.shields.io/badge/Version-1.0.0-blue)
![License](https://img.shields.io/badge/License-Apache%202.0-green)
![Python Version](https://img.shields.io/badge/Python-3.8+-yellow)
[![Documentation](https://img.shields.io/badge/Documentation-Latest-brightgreen)](https://github.com/xufengduan/Stimuli_generator)

</div>

<p align="center">
  <b>A Large Language Model-based Stimulus Material Generation Tool for Psycholinguistic Research</b>
</p>

---

## 📖 Project Introduction

Stimulus Generator is a tool based on large language models designed specifically for psycholinguistic research to generate stimulus materials. It can automatically generate experimental stimulus materials that meet requirements based on the experimental design and examples defined by researchers. This tool adopts a multi-agent architecture, including Generator, Validator, and Scorer, to ensure that the generated stimulus materials meet experimental requirements and are of high quality.

## ✨ Main Features

- **🤖 Multi-agent Architecture**:
  - **Generator**: Generates stimulus materials based on experimental design
  - **Validator**: Verifies whether the generated materials meet experimental requirements
  - **Scorer**: Scores materials in multiple dimensions

- **🔄 Flexible Model Selection**:
  - Supports GPT-4 (requires OpenAI API Key)
  - Supports Meta Llama 3.3 70B Instruct model

- **📊 Real-time Progress Monitoring**:
  - WebSocket real-time updates of generation progress
  - Detailed log information display
  - Generation process can be stopped at any time

- **🎨 User-friendly Interface**:
  - Intuitive form design
  - Real-time validation and feedback
  - Responsive layout design
  - Detailed help information

## 💻 System Requirements

| Requirement | Details |
|-------------|---------|
| Python | 3.8 or higher |
| Browser | Modern web browser (Chrome, Firefox, Safari, etc.) |
| Network | Stable network connection |
| Socket.IO | Client version 4.x (compatible with server side) |

## 🚀 Installation Instructions

### Clone directly from GitHub repository

```bash
# 1. Clone the project code
git clone https://github.com/xufengduan/Stimuli_generator.git
cd Stimuli_generator

# 2. Create and activate a virtual environment (recommended)
python -m venv venv

# Windows
venv\Scripts\activate
# Linux/Mac
source venv/bin/activate

# 3. Install required dependencies
pip install -e .
```

## 📝 Usage Instructions

### Launch Web Interface

After installation, you can use the command-line tool to start the web interface:

```bash
stimulus-generator webui
```
By default, the web interface will run at http://127.0.0.1:5000.

### Command Line Arguments

```bash
stimulus-generator webui --port 5001
```

| Argument | Description |
|----------|-------------|
| `--host` | Specify host address (default: 0.0.0.0) |
| `--port` | Specify port number (default: 5001) |
| `--debug` | Enable debug mode |
| `--share` | Create public link (requires additional dependencies) |

### Usage Steps

1. **Configure Generation Parameters**:
   - Select the language model to use
   - If using GPT-4, enter OpenAI API Key
   - Fill in experimental design description
   - Add example stimulus materials
   - Set validation conditions
   - Define scoring dimensions

2. **Start Generation**:
   - Click the "Generate stimulus" button to start generation
   - Monitor generation progress in real time
   - View detailed log information
   - Click the "Stop" button to terminate generation if necessary

3. **Get Results**:
   - Results file in CSV format will be automatically downloaded upon completion
   - Results file contains generated stimulus materials and their scores

## 📂 File Structure

```
Stimulus-Generator/
├── stimulus_generator/    # Main Python package
│   ├── __init__.py        # Package initialization file
│   ├── app.py             # Flask backend server
│   ├── backend.py         # Core backend functionality
│   └── cli.py             # Command line interface
├── run.py                 # Quick start script
├── setup.py               # Package installation configuration
├── static/
│   ├── script.js          # Frontend JavaScript code
│   ├── styles.css         # Page stylesheet
│   └── Stimulus Generator Web Logo.png  # Website icon
├── webpage.html           # Main page
├── requirements.txt       # Python dependency list
└── README.md              # Project documentation
```

## 🛠️ Command Line Tools

After installation, you can use the following command-line tools:

```bash
# Launch web interface
stimulus-generator webui [--host HOST] [--port PORT] [--debug] [--share]

# View help
stimulus-generator --help
```

If you don't want to install, you can also run directly:

```bash
# After cloning the repository, run in the project directory
python run.py webui
```

## ⚠️ Notes

1. **API Key Security**:
   - Please keep your OpenAI API Key secure
   - Do not expose API Keys in public environments

2. **Generation Process**:
   - Generation process may take some time, please be patient
   - You can monitor generation status in real time through the log panel
   - You can stop generation at any time if there are issues

3. **Results Usage**:
   - It is recommended to check if the generated materials meet experimental requirements
   - Manual screening or modification of generated materials may be needed

## ❓ FAQ

<details>
<summary><b>What to do if the generation process gets stuck?</b></summary>
<br>
- Check if the network connection is normal
- Click the "Stop" button to stop the current generation
- Refresh the page to restart
- If the page is unresponsive for a long time, wait for 30 seconds and the system will automatically unlock the interface
</details>

<details>
<summary><b>How to solve WebSocket connection errors?</b></summary>
<br>
- Ensure that the network environment does not block WebSocket connections
- If you see WebSocket error messages, refresh the page to re-establish the connection
- Restart the server or try using a different browser
- WebSocket connection issues will not affect main functionality, the system has automatic recovery mechanisms
</details>

<details>
<summary><b>How to optimize generation quality?</b></summary>
<br>
- Provide more detailed examples
- Improve experimental design description
- Set appropriate validation conditions
</details>

<details>
<summary><b>How to handle slow generation speed?</b></summary>
<br>
- Consider reducing the number of items to generate
- Ensure stable network connection
- Choose a model with faster response
</details>

## 📞 Technical Support

For questions or suggestions, please contact:
- Submit an [Issue](https://github.com/xufengduan/Stimuli_generator/issues)
- Send an email to: ...

## 📄 License

This project is licensed under the [Apache License 2.0](LICENSE). See the LICENSE file for details. 