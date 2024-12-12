import azure.cognitiveservices.speech as speechsdk
import time
import logging
import os
from datetime import datetime
from dotenv import load_dotenv
import requests

class QuotaChecker:
    def __init__(self):
        # Initialize configuration
        load_dotenv()
        self.setup_logging()
        
        self.speech_key = "kB8Tt5fBgJt7r1hz4P98qx5tq55I0gvugyjhfAzPyBmHTddnN6WJJQQJ99AJACL93NaXJ3w3AAAYACOGPMpm"
        self.service_region = "australiaeast"
        
        # Test settings
        self.test_attempts = 3
        self.retry_delay = 2

    def setup_logging(self):
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler('quota_check.log'),
                logging.StreamHandler()
            ]
        )
        self.logger = logging.getLogger(__name__)

    def check_quota_status(self):
        """
        Checks if the speech service quota is exceeded
        Returns: dict with quota status and details
        """
        self.logger.info("Starting quota status check")
        
        if not self.speech_key or not self.service_region:
            return {
                'quota_exceeded': None,
                'status': 'error',
                'message': 'Missing credentials',
                'details': 'Please check your .env file for AZURE_SPEECH_KEY and AZURE_SPEECH_REGION'
            }

        # Track attempts and results
        attempts_made = 0
        quota_exceeded = False
        last_error = None
        
        while attempts_made < self.test_attempts and not quota_exceeded:
            try:
                speech_config = speechsdk.SpeechConfig(
                    subscription=self.speech_key, 
                    region=self.service_region
                )
                
                # Create recognizer with default microphone
                audio_config = speechsdk.audio.AudioConfig(use_default_microphone=True)
                recognizer = speechsdk.SpeechRecognizer(
                    speech_config=speech_config,
                    audio_config=audio_config
                )

                # Test result storage
                done = False
                quota_error = False
                error_details = None

                def handle_result(evt):
                    nonlocal done
                    done = True

                def handle_canceled(evt):
                    nonlocal done, quota_error, error_details
                    details = evt.result.cancellation_details
                    if details.reason == speechsdk.CancellationReason.Error:
                        error_details = details.error_details
                        if "Quota exceeded" in error_details:
                            quota_error = True
                    done = True

                # Connect event handlers
                recognizer.recognized.connect(handle_result)
                recognizer.canceled.connect(handle_canceled)

                # Perform recognition test
                recognizer.recognize_once()

                # Wait for result
                while not done:
                    time.sleep(0.1)

                if quota_error:
                    quota_exceeded = True
                    last_error = error_details
                else:
                    # If successful, stop testing
                    return {
                        'quota_exceeded': False,
                        'status': 'success',
                        'message': 'Service quota is not exceeded',
                        'details': 'Speech service is working normally'
                    }

            except Exception as e:
                last_error = str(e)
                if "Quota exceeded" in last_error:
                    quota_exceeded = True
                else:
                    self.logger.error(f"Test attempt {attempts_made + 1} failed: {last_error}")

            attempts_made += 1
            if not quota_exceeded and attempts_made < self.test_attempts:
                time.sleep(self.retry_delay)

        if quota_exceeded:
            return {
                'quota_exceeded': True,
                'status': 'warning',
                'message': 'Service quota is exceeded',
                'details': last_error
            }
        else:
            return {
                'quota_exceeded': None,
                'status': 'error',
                'message': 'Test failed',
                'details': last_error
            }

def print_recommendations(result):
    """Print relevant recommendations based on the check result"""
    print("\nRecommendations:")
    if result['quota_exceeded']:
        print("1. Wait for your quota to reset (usually happens at the start of your billing cycle)")
        print("2. Consider upgrading your service tier for higher quotas")
        print("3. Review your usage patterns in the Azure portal")
        print("4. Implement rate limiting in your application")
        print("5. Contact Azure support if you need immediate quota increase")
    elif result['quota_exceeded'] is False:
        print("1. Monitor your usage regularly to avoid hitting quota limits")
        print("2. Set up alerts in Azure Monitor for quota metrics")
    else:
        print("1. Verify your credentials in the .env file")
        print("2. Check if your service is properly provisioned in Azure")
        print("3. Ensure your network connection is stable")

def main():
    checker = QuotaChecker()
    
    print("\nChecking Azure Speech Service Quota Status...")
    result = checker.check_quota_status()
    
    print("\nResults:")
    print(f"Status: {result['status'].upper()}")
    print(f"Message: {result['message']}")
    
    if result['quota_exceeded'] is not None:
        print(f"\nQuota Exceeded: {'Yes' if result['quota_exceeded'] else 'No'}")
    
    if result['details']:
        print(f"Details: {result['details']}")
        
    print_recommendations(result)

if __name__ == "__main__":
    main()