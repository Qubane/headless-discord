import re
import json
import asyncio
import argparse
import websockets
from typing import Any
from random import random
from datetime import datetime


parser = argparse.ArgumentParser(
    prog="HeadlessDiscord",
    description="Terminal version of discord")
parser.add_argument("auth", help="authentication token (your discord token)")
args = parser.parse_args()


class Member:
    """
    Guild member class
    """

    def __init__(self, **kwargs):
        self.guild_id: str | None = kwargs.get("guild_id")
        self.nick: str | None = kwargs.get("nick")
        self.mute: bool | None = kwargs.get("mute")
        self.deaf: bool | None = kwargs.get("deaf")
        self.joined_at: datetime = datetime.fromisoformat(kwargs.get("joined_at")) if "joined_at" in kwargs else None
        self.roles: list[str] | None = kwargs.get("roles")


class User:
    """
    Broad user class
    """

    def __init__(self, **kwargs):
        # general data
        self.id: str | None = kwargs.get("id")
        self.username: str | None = kwargs.get("username")

        # guild data
        self.member: Member | None = Member(**(kwargs["member"])) if "member" in kwargs else None

    @staticmethod
    def from_response(response: dict):
        """
        Generates user instance from discord response
        :return: User
        """

        user = User(
            **(response["author"]),
            member=response.get("member", {}))
        if "guild_id" in response:
            user.member.guild_id = response["guild_id"]

        return user

    @staticmethod
    def from_response_mention(mention: dict):
        """
        Generates user instance from discord mention response
        :return: User
        """

        return User(**mention)


class Message:
    """
    Message class
    """

    def __init__(self, **kwargs):
        # general data
        self.id: str | None = kwargs.get("id")
        self.channel_id: str | None = kwargs.get("channel_id")
        self.timestamp: datetime | None = datetime.fromisoformat(
            kwargs.get("timestamp")) if "timestamp" in kwargs else None
        self.author: User | None = User.from_response(kwargs)
        self.mentions: list[User] = [User.from_response_mention(x) for x in kwargs["mentions"]]
        self.content: str = kwargs.get("content")

        # guild data
        self.guild_id: str | None = kwargs.get("guild_id")

    @staticmethod
    def from_response(response: dict):
        """
        Generates message instance from discord response
        :return: Message
        """

        return Message(**response)

    def __str__(self):
        if self.guild_id:
            return f"[{self.timestamp.strftime('%H:%M:%S')}] {self.author.member.nick}> {self.content}"
        return f"[{self.timestamp.strftime('%H:%M:%S')}] {self.author.username}> {self.content}"


class Channel:
    """
    Channel class
    """

    def __init__(self, **kwargs):
        self.id: str = kwargs.get("id")
        self.name: str = kwargs.get("name")
        self.nsfw: bool = kwargs.get("nsfw")


class Guild:
    """
    Guild class
    """

    def __init__(self, **kwargs):
        self.id: str = kwargs.get("id")
        self.channels: list[Channel] = [Channel(**x) for x in kwargs["channels"]]
        self.member_count: int = kwargs.get("member_count")
        # TODO: add threads


class Client:
    def __init__(self):
        self._auth_token: str | None = None
        self._socket: websockets.WebSocketClientProtocol | None = None

        self.user: User | None = None
        self.guilds: list[Guild] | None = None

        self._heartbeat_interval = None
        self._sequence = None

    def run(self, token: str) -> None:
        """
        Connects the client
        """

        self._auth_token = token

        async def coro():
            async with websockets.connect("wss://gateway.discord.gg/?v=9&encoding=json") as websocket:
                self._socket = websocket
                self._heartbeat_interval = (await self.get_request())["d"]["heartbeat_interval"]

                await self.send_request(
                    {
                        "op": 2,
                        "d": {
                            "token": self._auth_token,
                            "capabilities": 16381,
                            "properties": {
                                "os": "Windows",
                                "browser": "Chrome",
                                "device": "",
                                "system_locale": "en-US",
                                "browser_user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                                                      "(KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
                                "browser_version": "123.0.0.0",
                                "os_version": "10",
                                "referrer": "https://search.brave.com/",
                                "referring_domain": "search.brave.com",
                                "referrer_current": "",
                                "referring_domain_current": "",
                                "release_channel": "stable",
                                "client_build_number": 281369,
                                "client_event_source": None
                            }
                        }
                    }
                )

                print("Connection successful.\n")
                await asyncio.gather(
                    self.process_heartbeat(),
                    self.process_input())

        print("Attempting connect...")
        try:
            asyncio.run(coro())
        except KeyboardInterrupt:
            pass
        except OSError:
            print("\nConnection failed!")
        print("\nConnection closed.")

    async def process_input(self) -> None:
        """
        Processes gateways input things
        """

        while True:
            response = await self.get_request()
            self._sequence = response["s"]

            # ready
            if response["t"] == "READY":
                self.user = User(**(response["d"]["user"]))
                self.guilds = [Guild(**x) for x in response["d"]["guilds"]]

            # messages
            elif response["t"] == "MESSAGE_CREATE":
                message = Message.from_response(response["d"])

            # opcode 1
            elif response["op"] == 1:
                await self.send_heartbeat()

            # anything else
            else:
                with open("big.json", "a", encoding="utf8") as file:
                    file.write(json.dumps(response, indent=2) + "\n\n")

    @staticmethod
    def message(response: dict):
        """
        Processes the message
        """

        message_timestamp = datetime.fromisoformat(response["d"]["timestamp"])
        message_author = response["d"]["author"]
        message_content = response["d"]["content"]

        if response["d"]["mentions"]:
            mentions = re.findall(r"<(.*?)>", message_content)
            for mention_id in mentions:
                mention_username = None
                for user in response["d"]["mentions"]:
                    if user["id"] == mention_id:
                        mention_username = user["username"]
                        break

                message_content = message_content.replace(f"<@{mention_id}>", mention_username)

        return f"[{message_timestamp.strftime('%H:%M:%S')}] {message_author['username']}> {message_content}"

    async def process_heartbeat(self) -> None:
        """
        Sends heartbeat event to opened gateway, to notify it that the app is running.
        Ran only once, when the connection is opened
        """

        # send heartbeat
        # wait `heartbeat_interval * jitter` as per discord docs
        await asyncio.sleep(self._heartbeat_interval * random() / 1000)
        await self.send_heartbeat()

        # continue the heartbeat
        while self._socket.open:
            await asyncio.sleep(self._heartbeat_interval)
            await self.send_heartbeat()

    async def send_heartbeat(self) -> None:
        """
        Sends heartbeat request to the gateway
        """

        await self.send_request({"op": 1, "d": self._sequence})

    async def send_request(self, request: Any) -> None:
        """
        Sends a request to connected socket
        """

        await self._socket.send(json.dumps(request))

    async def get_request(self) -> Any:
        """
        Gets request from connected socket
        """

        response = await self._socket.recv()
        if response:
            return json.loads(response)


def main():
    cli = Client()
    cli.run(args.auth)


if __name__ == '__main__':
    main()
