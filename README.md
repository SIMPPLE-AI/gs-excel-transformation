# gs-excel-transformation

Streamlit Community Cloud app: https://gs-excel-transformation.streamlit.app/

For the separate AWS Docker deployment, see the [deployment runbook](docs/deployment.md). It covers initial setup, manual updates, verification, rollback, and the Cloudflare handoff. Merging to `main` does not automatically deploy the AWS app.

## Important Notes
1. The time differences on this repo are meant for the Singapore time zone on the Streamlit server due to their time zone (UTC+0)
2. To test it locally, kindly ignore or adjust the `time_difference = timedelta(hours=9)` on the `utils.py` file

## How to use this Repository

1. At your project directory, clone this repo
```
git clone https://github.com/SIMPPLE-AI/gs-excel-transformation.git
```
2. Activate your venv

- Windows:
```
python -m venv venv & venv\Scripts\activate
```
- Linux:
```
python3 -m venv venv && source venv/bin/activate
```
3. Install the python dependencies for this project
```
pip install -r requirements.txt
```

## Running locally
1. Run the streamlit command
```
streamlit run app/main.py
```
