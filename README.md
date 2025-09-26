# Query Craft
 **An LLM based query crafter developed with Django framework**

## Key Features & Benefits

*   **Natural Language to SQL:** Converts natural language queries into SQL queries.
*   **LLM Powered:** Leverages the power of Large Language Models (LLMs) for accurate and intelligent query crafting.
*   **Dockerized:** Easily deployable using Docker containers.
*   **Web Interface:** Simple and intuitive web interface for users to interact with the system.

## Prerequisites & Dependencies

Before you begin, ensure you have the following installed:

*   **Docker:**  Required for containerization.  Install from [https://www.docker.com/](https://www.docker.com/)
*   **Docker Compose:** Required for orchestrating multi-container Docker applications. Install from [https://docs.docker.com/compose/install/](https://docs.docker.com/compose/install/)
*   **Python 3.11:**  The project is built using Python 3.11. Make sure it's installed on your system.

## Installation & Setup Instructions

1.  **Clone the repository:**

    ```bash
    git clone <repository_url>
    cd QueryCraft
    ```

2.  **Build and run the Docker containers:**

    ```bash
    docker-compose up --build
    ```

    This command will build the Docker image and start the application.

3.  **Access the application:**

    Once the containers are running, you can access the application in your web browser at `http://localhost:8000`.

## Usage Examples & API Documentation

Once the application is running:

1.  **Navigate to the web interface:** Open your web browser and go to `http://localhost:8000`.

2.  **Enter your natural language query:** Type your query into the provided text box.

3.  **Submit the query:** Click the "ASK" button.

4.  **View the generated SQL:** The generated SQL query will be displayed on the page.

Currently, there is no dedicated API documentation. However, the application structure is designed to be modular and extensible. Future versions may include a formalized API.

## Configuration Options

The following configuration options are available via environment variables (set in `docker-compose.yml` or your environment):

*   **DJANGO_SETTINGS_MODULE:** Specifies the Django settings module (default: `nl2sql_project.settings`).
*   **Other Django settings:** Refer to the Django documentation for configurable settings such as database connection details.


## License Information
License information is not yet specified for this project.
