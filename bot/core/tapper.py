import asyncio
import random
from urllib.parse import unquote, quote

import aiohttp
from aiocfscrape import CloudflareScraper
from aiohttp_proxy import ProxyConnector
from better_proxy import Proxy
from pyrogram import Client
from pyrogram.errors import Unauthorized, UserDeactivated, AuthKeyUnregistered, FloodWait
from pyrogram.raw.functions.messages import RequestAppWebView
from pyrogram.raw.types import InputBotAppShortName
from .agents import generate_random_user_agent
from bot.config import settings
from typing import Callable
from time import time
import functools
from bot.utils import logger
from bot.exceptions import InvalidSession
from .headers import headers


def speed_calc(referrals_count, time_since_last_boost):
    is_boost = True if time_since_last_boost < 3600 else False
    current_time = int(time())
    days_since_start = (current_time - 1724760000) // 86400
    speed = 0
    if referrals_count >= 300 and days_since_start >= 18:
        speed = 250
    elif referrals_count >= 200 and days_since_start >= 16:
        speed = 200
    elif referrals_count >= 100 and days_since_start >= 14:
        speed = 175
    elif referrals_count >= 50 and days_since_start >= 12:
        speed = 150
    elif referrals_count >= 25 and days_since_start >= 10:
        speed = 125
    elif referrals_count >= 10 and days_since_start >= 8:
        speed = 115
    elif referrals_count >= 5 and days_since_start >= 6:
        speed = 100
    elif referrals_count >= 4 and days_since_start >= 4:
        speed = 50
    elif referrals_count >= 3 and days_since_start >= 2:
        speed = 25
    elif referrals_count >= 1:
        speed = 10
    
    t = round(1583 + 1583 * speed / 100)
    
    return t * 2 if is_boost else t

def error_handler(func: Callable):
    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        try:
            return await func(*args, **kwargs)
        except Exception as e:
            await asyncio.sleep(1)
            logger.error(f"{args[0].session_name} | {func.__name__} error: {e}")
    return wrapper

class Tapper:
    def __init__(self, tg_client: Client, proxy: str):
        self.tg_client = tg_client
        self.session_name = tg_client.name
        self.proxy = proxy
        self.tg_web_data = None
        self.tg_client_id = 0

    async def get_tg_web_data(self) -> str:
        
        if self.proxy:
            proxy = Proxy.from_str(self.proxy)
            proxy_dict = dict(
                scheme=proxy.protocol,
                hostname=proxy.host,
                port=proxy.port,
                username=proxy.login,
                password=proxy.password
            )
        else:
            proxy_dict = None

        self.tg_client.proxy = proxy_dict

        try:
            if not self.tg_client.is_connected:
                try:
                    await self.tg_client.connect()

                except (Unauthorized, UserDeactivated, AuthKeyUnregistered):
                    raise InvalidSession(self.session_name)
            
            while True:
                try:
                    peer = await self.tg_client.resolve_peer('HorizonLaunch_bot')
                    break
                except FloodWait as fl:
                    fls = fl.value

                    logger.warning(f"{self.session_name} | FloodWait {fl}")
                    logger.info(f"{self.session_name} | Sleep {fls}s")
                    await asyncio.sleep(fls + 3)
            
            ref_id = random.choices([settings.REF_ID, "339631649"], weights=[75, 25], k=1)[0]
            web_view = await self.tg_client.invoke(RequestAppWebView(
                peer=peer,
                platform='android',
                app=InputBotAppShortName(bot_id=peer, short_name="HorizonLaunch"),
                write_allowed=True,
                start_param=ref_id
            ))

            auth_url = web_view.url
            tg_web_data = unquote(
                string=unquote(string=auth_url.split('tgWebAppData=')[1].split('&tgWebAppVersion')[0]))
            tg_web_data_parts = tg_web_data.split('&')
            
            user_data = tg_web_data_parts[0].split('=')[1]
            chat_instance = tg_web_data_parts[1].split('=')[1]
            chat_type = tg_web_data_parts[2].split('=')[1]
            start_param = tg_web_data_parts[3].split('=')[1]
            auth_date = tg_web_data_parts[4].split('=')[1]
            hash_value = tg_web_data_parts[5].split('=')[1]

            user_data_encoded = quote(user_data)

            init_data = (f"user={user_data_encoded}&chat_instance={chat_instance}&chat_type={chat_type}&"
                         f"start_param={start_param}&auth_date={auth_date}&hash={hash_value}")

            me = await self.tg_client.get_me()
            self.tg_client_id = me.id
            
            if self.tg_client.is_connected:
                await self.tg_client.disconnect()

            return init_data

        except InvalidSession as error:
            raise error

        except Exception as error:
            logger.error(f"{self.session_name} | Unknown error: {error}")
            await asyncio.sleep(delay=3)

    
    @error_handler
    async def make_request(self, http_client, method, endpoint=None, url=None, **kwargs):
        full_url = url or f"https://api.eventhorizongame.xyz{endpoint or ''}"
        async with http_client.request(method, full_url, **kwargs) as response:
            response.raise_for_status()
            response_json = await response.json()
            return response_json
    
    @error_handler
    async def login(self, http_client, init_data):
        return await self.make_request(http_client, 'POST', endpoint="/auth", json={'auth': init_data})
    
    @error_handler
    async def get_info(self, http_client, init_data):
        return await self.make_request(http_client, 'POST', endpoint=f"/tap", json={'auth': init_data})
       
    
    @error_handler
    async def boost(self, http_client, init_data):
        return await self.make_request(http_client, 'POST', endpoint="/tap?boost=true", json={'auth': init_data})
    
    @error_handler
    async def tap(self, http_client, init_data, tap_count):
        return await self.make_request(http_client, 'POST', endpoint=f"/taps?count={tap_count}", json={'auth': init_data})
        
        
    @error_handler
    async def check_proxy(self, http_client: aiohttp.ClientSession) -> None:
        response = await self.make_request(http_client, 'GET', url='https://httpbin.org/ip', timeout=aiohttp.ClientTimeout(5))
        ip = response.get('origin')
        logger.info(f"{self.session_name} | Proxy IP: <lc>{ip}</lc>")
        
        
    
    async def run(self) -> None:
        if settings.USE_RANDOM_DELAY_IN_RUN:
                random_delay = random.randint(settings.RANDOM_DELAY_IN_RUN[0], settings.RANDOM_DELAY_IN_RUN[1])
                logger.info(f"{self.session_name} | Bot will start in <m>{random_delay}s</m>")
                await asyncio.sleep(random_delay)
        
        
        proxy_conn = ProxyConnector().from_url(self.proxy) if self.proxy else None
        http_client = CloudflareScraper(headers=headers, connector=proxy_conn)
        if self.proxy:
            await self.check_proxy(http_client=http_client)
        
        if settings.FAKE_USERAGENT:            
            http_client.headers['User-Agent'] = generate_random_user_agent(device_type='android', browser_type='chrome')

        init_data = await self.get_tg_web_data()
        
        while True:
            try:
                if http_client.closed:
                    if proxy_conn:
                        if not proxy_conn.closed:
                            proxy_conn.close()

                    proxy_conn = ProxyConnector().from_url(self.proxy) if self.proxy else None
                    http_client = aiohttp.ClientSession(headers=headers, connector=proxy_conn)
                    if settings.FAKE_USERAGENT:            
                        http_client.headers['User-Agent'] = generate_random_user_agent(device_type='android', browser_type='chrome')  
                info_data = await self.login(http_client=http_client, init_data=init_data)
                if not info_data or not info_data.get('ok'):
                    logger.info(f"{self.session_name} | Login failed")
                    await asyncio.sleep(delay=1800)
                    continue
                await asyncio.sleep(2)

                rocket = info_data.get('rocket', {})
                user_info = info_data.get('user', {})
                logger.info(f"{self.session_name} | 🚀 Logged in successfully")
                last_boost_timestamp = int(rocket.get('last_boost_timestamp', time()))
                current_time = int(time())
                time_since_last_boost = current_time - last_boost_timestamp
                
                speed = speed_calc(user_info.get('referrals_count', 0), time_since_last_boost)
                logger.info(f"{self.session_name} | Name: <m>{user_info.get('name')}</m> | Points: <m>{int(rocket.get('distance', 0))}</m> | Speed: <m>{speed}</m>")
                
                boost_attempts = int(rocket.get('boost_attempts', 0))
                if last_boost_timestamp and boost_attempts:
                    if time_since_last_boost >= 3600 and boost_attempts < 7:
                        logger.info(f"{self.session_name} | More than an hour since last boost and <m>{boost_attempts}</m> attempts available")
                        boost = await self.boost(http_client=http_client, init_data=init_data)
                        if boost:
                            rocket = boost.get('rocket', {})
                            user_info = boost.get('user', {})
                            logger.info(f"{self.session_name} | <m>Boosted successfully</m>")
                            await asyncio.sleep(3)
                
                if time_since_last_boost <= 3600:
                    all_tap_count = int(rocket.get('boost_taps', 0))
                    while all_tap_count < 1000:
                        remaining_taps = 1000 - all_tap_count
                        tap_count = min(random.randint(30, 60), remaining_taps)
                        all_tap_count += tap_count

                        taps = await self.tap(http_client=http_client, init_data=init_data, tap_count=tap_count)
                        if taps:
                            rocket = taps.get('rocket', {})
                            user_info = taps.get('user', {})
                            logger.info(f"{self.session_name} | Tapped <m>{all_tap_count} / 1000</m> | Distance: <m>{int(rocket.get('distance', 0))}</m>")
                            sleep_time = random.randint(1, 3)
                            await asyncio.sleep(sleep_time)
                
                
                current_time = int(time())
                last_boost_timestamp = rocket.get('last_boost_timestamp', current_time)
                time_since_last_boost = max(0, current_time - last_boost_timestamp)
                time_since_last_boost = min(3600, time_since_last_boost)
                
                logger.info(f"{self.session_name} | Sleep <m>{time_since_last_boost}s</m>")
                
                await http_client.close()
                if proxy_conn:
                    if not proxy_conn.closed:
                        proxy_conn.close()
                await asyncio.sleep(delay=time_since_last_boost)
            except InvalidSession as error:
                raise error

            except Exception as error:
                logger.error(f"{self.session_name} | Unknown error: {error}")
                await asyncio.sleep(delay=3)
                logger.info(f'{self.session_name} | Sleep <m>600s</m>')
                await asyncio.sleep(600)
            
            
            
            

async def run_tapper(tg_client: Client, proxy: str | None):
    try:
        await Tapper(tg_client=tg_client, proxy=proxy).run()
    except InvalidSession:
        logger.error(f"{tg_client.name} | Invalid Session")
