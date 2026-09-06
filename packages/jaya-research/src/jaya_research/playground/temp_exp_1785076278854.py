import os
import time
import logging

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def retry_experiment(file_path, max_retries=3, retry_delay=1):
    """
    Retry an experiment with a corrected file path.

    Args:
        file_path (str): The corrected file path.
        max_retries (int, optional): The maximum number of retries. Defaults to 3.
        retry_delay (int, optional): The delay between retries in seconds. Defaults to 1.
    """
    retries = 0
    while retries < max_retries:
        try:
            # Run the experiment
            logger.info(f"Running experiment with file path: {file_path}")
            # Replace this comment with the actual experiment code
            # For example:
            # experiment_result = run_experiment(file_path)
            # logger.info(f"Experiment result: {experiment_result}")
            break
        except FileNotFoundError as e:
            logger.error(f"File not found: {e}")
            retries += 1
            if retries < max_retries:
                logger.info(f"Retrying in {retry_delay} seconds...")
                time.sleep(retry_delay)
            else:
                logger.error("Max retries exceeded. Giving up.")
                raise

def recursive_directory_traversal(root_dir):
    """
    Recursively traverse a directory and yield file paths.

    Args:
        root_dir (str): The root directory to start the traversal from.
    """
    for root, dirs, files in os.walk(root_dir):
        for file in files:
            yield os.path.join(root, file)

def run_evolution_sandbox():
    """
    Run the EvolutionSandbox with recursive directory traversal.
    """
    root_dir = "/path/to/evolution/sandbox"  # Replace with the actual root directory
    for file_path in recursive_directory_traversal(root_dir):
        retry_experiment(file_path)

if __name__ == "__main__":
    run_evolution_sandbox()