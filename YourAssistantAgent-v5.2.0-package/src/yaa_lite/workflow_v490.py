"""Final request boundary after the historical controller wrappers."""
_INSTALLED=False


def apply_workflow_v490():
    global _INSTALLED
    if _INSTALLED:return
    from .agent.intent import explicit_example_only
    from .agent.orchestrator import SmartAgentController,AgentResponse
    original=SmartAgentController.handle
    def handle(self,profile,history,user_text,session_id,max_tokens,timeout,status=None):
        if explicit_example_only(user_text):
            self.db.clear_pending_action(session_id)
            return AgentResponse(self.t('فهمت أنه مثال فقط؛ لم أفتح صفحة أو أجهّز نشراً. أعطني الطلب الفعلي عندما تريد التنفيذ.','Understood as an example only. No page opened or publishing plan created. Give the actual request when ready.'))
        return original(self,profile,history,user_text,session_id,max_tokens,timeout,status=status)
    SmartAgentController.handle=handle
    _INSTALLED=True
