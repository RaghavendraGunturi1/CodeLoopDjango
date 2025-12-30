from waitress import serve
from codingplatform.wsgi import application  # Replace 'your_project_name' with your actual folder name

if __name__ == '__main__':
    print("Serving on http://0.0.0.0:8000")
    # Threads=16 allows 16 simultaneous requests. Adjust based on your i7 cores.
    serve(application, host='0.0.0.0', port=8000, threads=16)