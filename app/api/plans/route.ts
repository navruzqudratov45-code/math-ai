import { NextResponse } from 'next/server';
import { dbCall } from '../../../lib/auth';
import { publicPaymentConfig } from '../../../lib/payments/config';
export async function GET() {
  try {
    const settings = await dbCall<Record<string, unknown>>({ op: 'settings' });
    const features = (key: 'freePlanFeatures' | 'premiumPlanFeatures', limit: unknown) => [
      `Kuniga ${Number(limit)} ta masala`, ...((Array.isArray(settings[key]) ? settings[key] as string[] : []).filter(item => !/^Kuniga \d+ ta masala$/.test(item)))];
    return NextResponse.json({ free: { code: 'free', dailyLimit: settings.freeDailyLimit, savedCapacity: settings.freeSavedCapacity, features: features('freePlanFeatures', settings.freeDailyLimit) },
      premium: { code: 'premium', dailyLimit: settings.premiumDailyLimit, savedCapacity: settings.premiumSavedCapacity, features: features('premiumPlanFeatures', settings.premiumDailyLimit),
        extendedExplanations: settings.premiumExtendedExplanations, priorityRouting: settings.premiumPriorityRouting }, payments: publicPaymentConfig() });
  } catch { return NextResponse.json({ error: 'Reja ma’lumotlarini yuklab bo‘lmadi.' }, { status: 503 }); }
}
