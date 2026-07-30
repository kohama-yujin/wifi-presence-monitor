from app import create_app

app = create_app()

if __name__ == "__main__":
    # ARPの送信には管理者権限とNpcapが必要です。
    app.run(host="0.0.0.0", port=5000)
