#!/usr/bin/env python
"""
环境变量配置模块 (v2.5.2 新增)

使用 pydantic-settings 对 .env 中的配置进行强类型检查，
防止因配置错误导致的运行时崩溃。

用法:
    from config.env_settings import env_settings
    webhook = env_settings.dingtalk_webhook
"""
from typing import Optional
import os

# 尝试使用 pydantic-settings，如果未安装则降级
try:
    from pydantic_settings import BaseSettings
    from pydantic import Field, field_validator
    HAS_PYDANTIC = True
except ImportError:
    HAS_PYDANTIC = False


if HAS_PYDANTIC:
    class EnvSettings(BaseSettings):
        """环境变量配置类 (带类型验证)"""
        
        # 钉钉机器人配置
        dingtalk_webhook: str = Field(
            default="",
            description="钉钉机器人 Webhook URL"
        )
        dingtalk_secret: str = Field(
            default="",
            description="钉钉机器人签名密钥"
        )
        
        # 企业微信机器人 (可选)
        wechat_webhook: str = Field(
            default="",
            description="企业微信机器人 Webhook URL"
        )
        
        # Server酱 (可选)
        serverchan_key: str = Field(
            default="",
            description="Server酱 SendKey"
        )
        
        # 开发模式
        debug: bool = Field(
            default=False,
            description="是否开启调试模式"
        )
        
        # 异步日志
        async_log: bool = Field(
            default=False,
            description="是否启用异步日志写入"
        )
        
        @field_validator('dingtalk_webhook')
        @classmethod
        def validate_webhook(cls, v: str) -> str:
            """验证 Webhook URL 格式"""
            if v and not v.startswith('https://'):
                raise ValueError(f"Webhook URL 必须以 https:// 开头: {v}")
            return v
        
        class Config:
            # 从 .env 文件读取
            env_file = ".env"
            env_file_encoding = "utf-8"
            # 忽略未知字段，兼容旧配置
            extra = "ignore"
    
    # 创建全局实例
    try:
        env_settings = EnvSettings()
    except Exception as e:
        # 配置加载失败，使用默认值
        print(f"⚠️ 环境变量配置加载失败: {e}")
        env_settings = EnvSettings.model_construct()

else:
    # pydantic-settings 未安装时的降级实现
    class EnvSettingsFallback:
        """降级版环境变量配置 (无类型验证)"""
        
        def __init__(self):
            from dotenv import load_dotenv
            load_dotenv()
            
            self.dingtalk_webhook = os.getenv('DINGTALK_WEBHOOK', '')
            self.dingtalk_secret = os.getenv('DINGTALK_SECRET', '')
            self.wechat_webhook = os.getenv('WECHAT_WEBHOOK', '')
            self.serverchan_key = os.getenv('SERVERCHAN_KEY', '')
            self.debug = os.getenv('DEBUG', 'false').lower() == 'true'
            self.async_log = os.getenv('ASYNC_LOG', 'false').lower() == 'true'
    
    env_settings = EnvSettingsFallback()


def validate_config() -> bool:
    """
    验证配置完整性
    
    Returns:
        是否配置完整且有效
    """
    warnings = []
    
    # 检查通知配置
    if not env_settings.dingtalk_webhook and not env_settings.wechat_webhook:
        warnings.append("未配置消息推送 (DINGTALK_WEBHOOK 或 WECHAT_WEBHOOK)")
    
    if env_settings.dingtalk_webhook and not env_settings.dingtalk_secret:
        warnings.append("钉钉 Webhook 已配置但缺少 DINGTALK_SECRET")
    
    if warnings:
        for w in warnings:
            print(f"⚠️ 配置警告: {w}")
        return False
    
    return True


if __name__ == "__main__":
    # 测试配置加载
    print("=== 环境变量配置测试 ===")
    print(f"DingTalk Webhook: {'已配置' if env_settings.dingtalk_webhook else '未配置'}")
    print(f"DingTalk Secret: {'已配置' if env_settings.dingtalk_secret else '未配置'}")
    print(f"Debug Mode: {env_settings.debug}")
    print(f"Async Log: {env_settings.async_log}")
    validate_config()
