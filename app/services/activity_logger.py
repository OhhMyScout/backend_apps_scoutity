from config.database import get_supabase_client

supabase = get_supabase_client()


class ActivityLogger:

    @staticmethod
    def log(activity: str, user_id: str = None, ip_address: str = None, user_agent: str = None):
        """
        Logger aman tanpa dependency Flask request context.
        Bisa dipakai di FastAPI / Flask / service / background job.
        """

        try:
            log_data = {
                "activity": activity,
                "ip_address": ip_address or "unknown",
                "user_agent": user_agent or "unknown",
            }

            # hanya simpan jika user_id ada
            if user_id:
                log_data["user_id"] = str(user_id)

            # insert ke Supabase
            supabase.table("activity_logs").insert(log_data).execute()

        except Exception as e:
            print("[ACTIVITY LOG ERROR]", str(e))