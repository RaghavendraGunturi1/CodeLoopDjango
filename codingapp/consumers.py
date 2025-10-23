# In codingapp/consumers.py
import json
from channels.generic.websocket import AsyncWebsocketConsumer

class SubmissionConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        # Get the submission ID from the URL requested by the browser
        self.submission_id = self.scope['url_route']['kwargs']['submission_id']
        self.submission_group_name = f'submission_{self.submission_id}'

        # Each submission gets its own "chat room".
        # The user's browser joins this room.
        await self.channel_layer.group_add(
            self.submission_group_name,
            self.channel_name
        )

        await self.accept()

    async def disconnect(self, close_code):
        # Leave the room when the connection closes
        await self.channel_layer.group_discard(
            self.submission_group_name,
            self.channel_name
        )

    # This function is called when a message is sent to the room
    async def submission_update(self, event):
        # Send the final results from the Celery task to the browser
        await self.send(text_data=json.dumps({
            'status': event['status'],
            'results': event['results'],
        }))