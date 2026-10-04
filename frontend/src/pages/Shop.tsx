import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { api } from '../api'
import { useStore } from '../store'

declare global { interface Window { Razorpay: any } }

export default function Shop() {
  const { user, showToast } = useStore()
  const products = useQuery({ queryKey: ['products'], queryFn: () => api.get<any[]>('/shop/products') })
  const [cart, setCart] = useState<Record<string, number>>({})
  const [cat, setCat] = useState('All')

  const cats = ['All', 'Protein', 'Vitamins', 'Food', 'Gear']
  const items = (products.data || []).filter((p) => cat === 'All' || p.cat === cat)
  const count = Object.values(cart).reduce((s, q) => s + q, 0)
  const subtotal = (products.data || []).reduce((s, p) => s + (cart[p.id] || 0) * p.price, 0)
  const total = subtotal - Math.round(subtotal * 0.15)

  async function checkout() {
    try {
      const body = { items: Object.entries(cart).map(([product_id, qty]) => ({ product_id, qty })) }
      const r = await api.post<any>('/shop/checkout', body)
      if (r.razorpay.mock || !window.Razorpay) {
        await api.post('/shop/verify-payment', { order_id: r.order_id, razorpay_order_id: r.razorpay.order_id, razorpay_payment_id: 'pay_mock', razorpay_signature: 'mock' })
        setCart({}); showToast('Order confirmed (test mode)')
        return
      }
      const rzp = new window.Razorpay({
        key: r.razorpay.key_id, amount: r.razorpay.amount, currency: 'INR', order_id: r.razorpay.order_id,
        name: 'Reps & Greens', prefill: { name: user?.name, email: user?.email }, theme: { color: '#3E9B5F' },
        handler: async (resp: any) => {
          await api.post('/shop/verify-payment', {
            order_id: r.order_id, razorpay_order_id: resp.razorpay_order_id,
            razorpay_payment_id: resp.razorpay_payment_id, razorpay_signature: resp.razorpay_signature,
          })
          setCart({}); showToast('Payment verified · order confirmed')
        },
      })
      rzp.open()
    } catch (e: any) { showToast(e.message) }
  }

  return (
    <div className="pt-2 pb-6">
      <p className="text-[11px] font-bold uppercase tracking-wide text-inksoft">Shop</p>
      <h1 className="mb-4 font-disp text-2xl font-extrabold">Coach-approved fuel</h1>
      <div className="mb-4 flex gap-2 overflow-x-auto">
        {cats.map((c) => (
          <button key={c} onClick={() => setCat(c)} className={`shrink-0 rounded-full border px-4 py-2 text-sm font-semibold ${cat === c ? 'border-ink bg-ink text-canvas' : 'border-line bg-card text-inksoft'}`}>{c}</button>
        ))}
      </div>
      <div className="grid grid-cols-2 gap-3">
        {items.map((p) => (
          <div key={p.id} className="card overflow-hidden">
            <div className="grid aspect-square place-items-center bg-tint text-3xl font-extrabold text-inksoft">{p.name[0]}</div>
            <div className="p-3">
              <p className="min-h-[34px] text-[13px] font-bold leading-tight">{p.name}</p>
              <p className="my-1.5 font-num font-bold">₹{p.price.toLocaleString('en-IN')} <s className="text-xs text-inksoft">₹{p.mrp?.toLocaleString('en-IN')}</s></p>
              <button onClick={() => setCart((c) => ({ ...c, [p.id]: (c[p.id] || 0) + 1 }))} className="w-full rounded-xl bg-tint py-2 text-sm font-bold active:scale-95">
                {cart[p.id] ? `In cart × ${cart[p.id]}` : '+ Add'}
              </button>
            </div>
          </div>
        ))}
      </div>
      {count > 0 && (
        <button onClick={checkout} className="btn btn-ink mt-5">Checkout · {count} items · ₹{total.toLocaleString('en-IN')}</button>
      )}
    </div>
  )
}
