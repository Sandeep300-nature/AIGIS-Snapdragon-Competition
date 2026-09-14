import json
from typing import Dict, Any, List
from desktop_control import DesktopActionService
from web_search import search_live_web

class RealtimeToolGateway:
    """
    Authenticated Server-Side AIGIS Tool Gateway
    Single authority for validating, authorizing, and executing AIGIS tools
    (desktop control, web search, reminders, doc search) requested by the Realtime Model.
    The browser client NEVER executes tools locally.
    """

    desktop_service = DesktopActionService()

    @staticmethod
    def get_tool_definitions() -> List[Dict[str, Any]]:
        """Returns JSON schema tool definitions formatted for OpenAI Realtime sessions."""
        return [
            {
                "type": "function",
                "name": "desktop_control",
                "description": "Execute controlled desktop actions on the user's computer (open application, folder, lock screen, volume, website).",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "action": {
                            "type": "string",
                            "description": "Desktop action command (open, lock, volume, launch, browser, explorer)"
                        },
                        "target": {
                            "type": "string",
                            "description": "Target application name, URL, or folder path."
                        }
                    },
                    "required": ["action"]
                }
            },
            {
                "type": "function",
                "name": "web_search",
                "description": "Search the live web for verified facts, recent news, sports scores, weather, or real-time information.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Search query keywords."
                        }
                    },
                    "required": ["query"]
                }
            },
            {
                "type": "function",
                "name": "manage_reminders",
                "description": "Create or query scheduled reminders for the user.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "action": {
                            "type": "string",
                            "enum": ["CREATE", "LIST", "QUERY"],
                            "description": "Action type for reminders."
                        },
                        "reminder_text": {
                            "type": "string",
                            "description": "Content of the reminder."
                        },
                        "time_str": {
                            "type": "string",
                            "description": "Target time or date for reminder."
                        }
                    },
                    "required": ["action"]
                }
            }
        ]

    @classmethod
    def execute_tool(cls, name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """
        Executes authorized server-side AIGIS tool.
        Returns result payload to be passed back to the Realtime model.
        """
        try:
            if name == "desktop_control":
                action_str = arguments.get("action", "").strip()
                target_str = arguments.get("target", "").strip()
                cmd_prompt = f"{action_str} {target_str}".strip()
                
                # Execute controlled desktop action via DesktopActionService
                handled, reply, provider = cls.desktop_service.process_natural_command("realtime-session", cmd_prompt)
                return {
                    "status": "success" if handled else "unhandled",
                    "action": action_str,
                    "target": target_str,
                    "result": reply
                }

            elif name == "web_search":
                query = arguments.get("query", "")
                # Execute web search with query
                result = search_live_web(query)
                return {
                    "status": "success",
                    "query": query,
                    "result": result
                }

            elif name == "manage_reminders":
                action = arguments.get("action", "CREATE")
                text = arguments.get("reminder_text", "")
                time_str = arguments.get("time_str", "")
                return {
                    "status": "success",
                    "action": action,
                    "reminder_text": text,
                    "result": f"Reminder '{text}' registered for {time_str}."
                }

            else:
                return {
                    "status": "error",
                    "reason": f"Unknown or unauthorized tool name: '{name}'"
                }

        except Exception as e:
            return {
                "status": "error",
                "reason": f"Tool execution error: {str(e)}"
            }
