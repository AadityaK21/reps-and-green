# Merova Fit security notes

What protects the app, and the few settings that keep it that way.

## Payments (Razorpay)

- A payment only counts for the exact Razorpay order the server created for that order or plan. A signature from a different (cheaper) order is refused.
- Each payment ID can be used once. Verify and webhook can race; the order or plan is still fulfilled exactly once.
- Starting a plan checkout never removes Premium someone already has. A free trial can't replace a paid plan.
- The webhook (`/shop/webhook`) confirms shop orders **and** plans, so a payment still lands if the app closes mid-checkout. Set `RAZORPAY_WEBHOOK_SECRET` and add the webhook in the Razorpay dashboard for `payment.captured` and `order.paid`.
- The Razorpay **key secret** lives only in Render's environment. The key ID in the app is public by design.

## Accounts

- Passwords are bcrypt-hashed. Sign-in codes are 6 digits, valid 10 minutes, 5 tries each.
- Rate limits apply per IP **and** per email: 10 password tries per 15 minutes, 5 codes per hour, 3 reset emails per hour.
- If someone registers an email they don't own, the real owner takes it back by signing in with an emailed code or Google: the earlier password and sessions stop working.
- Reset links expire after 30 minutes and are single-use; using one signs out every device.
- Logging out (or "sign out other devices") ends access immediately, including the live-update socket.
- A refresh token used twice means it was copied, so the whole login is ended.
- Apple sign-in stays off until `APPLE_CLIENT_ID` is set.

## Abuse limits

- Bookings: 6 per hour, 10 open at most. WhatsApp texts are built only from fixed wording plus a validated time, so nobody can send their own words from the business number.
- Phone numbers must look like real numbers (10–14 digits).
- Chat: 20 messages a minute for clients. Uploads: 20 an hour, 300 files per person.
- Every input has length and range limits (names, meals, weights, dates, passwords).

## Privacy

- Deleting an account removes logs, chats, bookings, cart, photos, sessions and codes. Orders and payment records stay because tax law requires them.
- Progress photos are served only to their owner and the coach.
- `/health` only says whether the server is up. Details are at `/admin/health` (coach/admin only).
- Request logs never include query strings, so socket tokens don't end up in Render's logs.

## Settings to check in Render

| Setting | Why |
| --- | --- |
| `ENV=production` | Turns off API docs and test-mode payments |
| `JWT_SECRET` | 32+ random characters (Render generates it). The app refuses to start otherwise |
| `COACH_PASSWORD` | 12+ characters with upper, lower, number and symbol |
| `RAZORPAY_WEBHOOK_SECRET` | Needed for the webhook above |
| `FRONTEND_ORIGIN` | `https://fit.merova.app`, so only your site can call the API from a browser |
| `CLIENT_IP_MODE` | Sign in as the coach, open `/admin/debug/ip`, and use the mode whose value is your real IP |

## Still worth doing later

- Verify phone numbers with a WhatsApp/SMS code before sending messages to them.
- Move to Render's paid plan plus Redis before running more than one server, so rate limits and live chat are shared.
- If progress photos move to S3 or Cloudinary, keep the bucket private and serve photos through `/files/{id}`.
- Rotate any key that was ever pasted into a chat, email or screenshot.
