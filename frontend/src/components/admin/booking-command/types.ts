export interface BookingData {
  kpis: {
    total_bookings: number;
    confirmed: number;
    cancelled: number;
    today_bookings: number;
    week_bookings: number;
    active_pages: number;
    total_pages: number;
    upcoming_count: number;
    reminders_sent: number;
    conversion_rate: number;
    cancel_rate: number;
    weekly_sparkline?: number[];
  };
  daily_chart: { date: string; count: number }[];
  peak_hours: { hour: number; count: number }[];
  top_hosts: { user_id: string; name: string; email: string; total: number; confirmed: number; cancelled: number }[];
  upcoming: { booking_id: string; guest_name: string; guest_email: string; start: string }[];
  recent_bookings: Booking[];
}

export interface Booking {
  booking_id: string;
  guest_name: string;
  guest_email: string;
  host_name?: string;
  start: string;
  status: string;
}

export type BookingFilter = 'all' | 'confirmed' | 'cancelled';

export const fmtDt = (s: string) => {
  try {
    return new Date(s).toLocaleDateString([], { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
  } catch {
    return s;
  }
};
