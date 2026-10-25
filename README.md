# TaskFlow AI — dự án học Backend FastAPI

Dự án quản lý công việc cho nhân viên: đăng ký, đăng nhập, tạo và giao việc, cập nhật tiến độ, và hỏi chatbot AI về những công việc mình được phép xem. Có giao diện web đơn giản tại `/` để thử API; trọng tâm học là code backend.

## Chạy nhanh

Yêu cầu Python 3.11+.

```bash
cd "FastAPI Task Manager AI"
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload
```

Mở `http://127.0.0.1:8000/` để dùng ứng dụng và `http://127.0.0.1:8000/docs` để xem hợp đồng API. Database mới ban đầu chỉ có các bảng rỗng; chưa có tài khoản hoặc công việc mẫu.

**Chatbot dùng OpenAI:** điền `OPENAI_API_KEY` vào `.env` và chọn model tài khoản của bạn có quyền truy cập qua `OPENAI_MODEL`. API key chỉ nằm ở backend. Nếu chưa có key, đặt `AI_MODE=demo` rồi khởi động lại server; chatbot sẽ trả lời bằng quy tắc mẫu và hiển thị rõ đây là chế độ demo. Chế độ mặc định `AI_MODE=openai` trả HTTP 503 cho `/api/chat` khi thiếu key, không giả vờ là AI thật. Code gọi [Responses API theo OpenAI Docs](https://developers.openai.com/api/docs/guides/text).

### Dùng PostgreSQL trên Supabase

Dự án dùng SQLAlchemy nên có thể đổi `DATABASE_URL` từ SQLite sang PostgreSQL của Supabase. Vào **Supabase Dashboard → Connect**, sao chép URL **Direct connection** cho backend có IPv6 (hoặc gói có IPv4 add-on); nếu mạng chỉ có IPv4, chọn **Session pooler** ở cổng 5432. Dán URL vào `.env`, thay mật khẩu mẫu và thêm `sslmode=require`:

```env
DATABASE_URL=postgresql://postgres.<PROJECT_REF>:<PASSWORD>@<POOLER_HOST>:5432/postgres?sslmode=require
```

Đây chỉ là **mẫu hình dạng URL**: lấy hostname, username và port thực tế từ nút Connect của dự án, không tự ghép địa chỉ. Nếu mật khẩu có ký tự đặc biệt như `@`, `#`, `?`, `&` thì cần URL-encode. Dự án tự đổi tiền tố `postgresql://` sang driver `postgresql+psycopg://`. Khởi động lại server để SQLAlchemy tạo các bảng còn thiếu. Giữ `.env` ngoài Git và chỉ dùng URL database tại backend. Supabase khuyên dùng SSL; có thể cấu hình xác thực chứng chỉ mạnh hơn bằng `sslmode=verify-full` và CA của dự án. Xem [hướng dẫn kết nối của Supabase](https://supabase.com/docs/guides/database/connecting-to-postgres).

Việc đổi database **không tự chuyển dữ liệu** từ file SQLite cũ sang Supabase. Đăng nhập vẫn dùng bảng `users` và `login_sessions` của dự án, chưa dùng Supabase Auth. Với ứng dụng thật, hãy thay `create_all()` bằng migration Alembic trước khi thay đổi schema.

## Quy trình đăng ký, đăng nhập và sử dụng

### Trên giao diện web

1. **Tạo tài khoản nhân viên:** mở `http://127.0.0.1:8000/`, chọn **Đăng ký**, nhập họ tên, email và mật khẩu từ 10 ký tự. Sau khi đăng ký thành công, giao diện tự đăng nhập. Email đã tồn tại sẽ bị từ chối.
2. **Đăng nhập lần sau:** chọn **Đăng nhập**, nhập email và mật khẩu. Backend kiểm tra mật khẩu đã hash và cấp cookie phiên `task_session` dạng HttpOnly, có hạn 7 ngày. Trình duyệt tự gửi cookie cho các yêu cầu `/api`; không cần nhập lại mật khẩu cho từng thao tác.
3. **Tạo và giao công việc:** trong mục **Danh sách công việc**, nhập tên, mô tả, người thực hiện, mức ưu tiên và hạn hoàn thành rồi bấm **Tạo công việc**. Nếu tự làm, chọn tên mình. Danh sách nhân viên chỉ xuất hiện sau khi họ đã đăng ký.
4. **Theo dõi và cập nhật:** cả người tạo và người được giao đều thấy công việc trong danh sách của mình, có thể đổi trạng thái **Cần làm → Đang làm → Hoàn thành**. Chỉ người tạo được sửa tên, mô tả, ưu tiên, hạn, người được giao hoặc xóa công việc.
5. **Hỏi chatbot:** nhập câu hỏi như “Tôi còn việc ưu tiên cao nào?” ở mục **Trợ lý công việc**. Backend lấy các công việc người đang đăng nhập được quyền xem rồi mới gửi context cho OpenAI. Trợ lý chỉ trả lời, không tạo hoặc sửa công việc. Lịch sử chat chỉ hiển thị cho chính tài khoản đó.
6. **Đăng xuất:** bấm **Đăng xuất** để hủy phiên ở database và xóa cookie. Các API công việc và chatbot sẽ trả `401` cho đến khi đăng nhập lại.

Để thử luồng giao việc giữa hai nhân viên, tạo tài khoản Lan và Minh trong **hai trình duyệt hoặc hai hồ sơ trình duyệt riêng**. Hai tab cùng một trình duyệt thường dùng chung cookie đăng nhập nên sẽ không duy trì hai tài khoản độc lập.

### Gọi API trực tiếp để học backend

Các lệnh dưới đây giả sử server đang chạy trên `127.0.0.1:8000`. Đăng ký trước, sau đó đăng nhập và lưu cookie phiên vào file tạm:

```bash
curl -X POST http://127.0.0.1:8000/api/auth/register \
  -H 'Content-Type: application/json' \
  -d '{"name":"Lan","email":"lan@example.com","password":"password1234"}'

curl -X POST http://127.0.0.1:8000/api/auth/login \
  -H 'Content-Type: application/json' \
  -c /tmp/taskflow-cookies.txt \
  -d '{"email":"lan@example.com","password":"password1234"}'
```

Dùng `-b /tmp/taskflow-cookies.txt` cho các yêu cầu cần đăng nhập. Xem ID nhân viên ở `/api/users` trước khi giao việc; bỏ `assignee_id` nếu muốn tự nhận:

```bash
curl -b /tmp/taskflow-cookies.txt http://127.0.0.1:8000/api/users

curl -X POST http://127.0.0.1:8000/api/tasks \
  -H 'Content-Type: application/json' \
  -b /tmp/taskflow-cookies.txt \
  -d '{"title":"Chuẩn bị báo cáo tuần","description":"Tổng hợp tiến độ","priority":"high","due_date":"2026-11-01"}'

curl -b /tmp/taskflow-cookies.txt http://127.0.0.1:8000/api/tasks

curl -X PATCH http://127.0.0.1:8000/api/tasks/1 \
  -H 'Content-Type: application/json' \
  -b /tmp/taskflow-cookies.txt \
  -d '{"status":"doing"}'

curl -X POST http://127.0.0.1:8000/api/chat \
  -H 'Content-Type: application/json' \
  -b /tmp/taskflow-cookies.txt \
  -d '{"message":"Tôi nên ưu tiên công việc nào?"}'

curl -X POST -b /tmp/taskflow-cookies.txt http://127.0.0.1:8000/api/auth/logout
```

Thay `/api/tasks/1` bằng ID công việc nhận được sau khi tạo. Nếu chưa cấu hình OpenAI, đặt `AI_MODE=demo` trong `.env` rồi khởi động lại server trước khi thử `/api/chat`; nếu giữ `AI_MODE=openai` mà không có key, endpoint này trả `503`.


## Chức năng và quyền

| Chức năng | Quyền |
| --- | --- |
| Đăng ký, đăng nhập, đăng xuất | Bất kỳ người dùng nào; đăng ký mở cho mục đích học tập |
| Xem danh sách nhân viên | Người đã đăng nhập; chỉ trả ID và tên |
| Tạo công việc, chọn người được giao | Người đã đăng nhập |
| Xem công việc | Người tạo hoặc người được giao |
| Sửa nội dung, ưu tiên, hạn, người được giao; xóa | Người tạo |
| Đổi trạng thái | Người tạo hoặc người được giao |
| Hỏi chatbot, xem lịch sử chat | Người đã đăng nhập; dữ liệu tách theo tài khoản |

Chatbot chỉ nhận tối đa 50 công việc mới nhất mà người hỏi được quyền xem, 6 tin nhắn gần nhất và tối đa 2.000 ký tự câu hỏi. Chatbot **chỉ đọc và tư vấn**, không tự sửa database. Giới hạn mặc định 30 lượt gọi/người/giờ để kiểm soát chi phí. Chỉ dùng dữ liệu thử nghiệm khi học.

## API chính

| Method | Endpoint | Ý nghĩa |
| --- | --- | --- |
| `POST` | `/api/auth/register` | Tạo tài khoản |
| `POST` | `/api/auth/login` | Đăng nhập, cấp cookie phiên HttpOnly |
| `POST` | `/api/auth/logout` | Hủy phiên |
| `GET` | `/api/auth/me` | Xem tài khoản hiện tại |
| `GET` | `/api/users` | Lấy danh sách người được giao |
| `GET`, `POST` | `/api/tasks` | Liệt kê, tạo việc |
| `GET`, `PATCH`, `DELETE` | `/api/tasks/{id}` | Xem, sửa, xóa việc |
| `GET` | `/api/chat/history` | Lịch sử chatbot cá nhân |
| `POST` | `/api/chat` | Hỏi chatbot |

## Cấu trúc code

```text
app/
  main.py          # FastAPI routes, dependency và phân quyền
  schemas.py       # Request/response Pydantic
  models.py        # Bảng SQLAlchemy
  database.py      # Engine và session database
  dependencies.py  # DB session và xác thực người dùng
  ai_service.py    # Lời gọi OpenAI, prompt, chế độ demo
  config.py        # Đọc cấu hình môi trường
  static/           # Giao diện để thử API
tests/test_app.py  # Test luồng đăng nhập, phân quyền, chatbot
```

Sơ đồ một yêu cầu: **trình duyệt → FastAPI route → Pydantic validation → dependency xác thực → SQLAlchemy/database → response**. Riêng `/api/chat` gọi thêm `ai_service.py` sau khi backend đã lọc công việc theo quyền.

## Phạm vi triển khai

Đây là dự án học tập chạy cục bộ. Trước khi dùng với dữ liệu công ty thật, cần thêm cơ chế mời nhân viên hoặc SSO thay cho đăng ký mở, HTTPS và `COOKIE_SECURE=true`, migration database, quản lý bí mật, audit log, rate limit dùng chung giữa nhiều server, quy trình xử lý dữ liệu gửi sang nhà cung cấp AI và kiểm thử bảo mật. SQLite phù hợp để học và demo; PostgreSQL phù hợp hơn khi nhiều nhân viên truy cập đồng thời.
