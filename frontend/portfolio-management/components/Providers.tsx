'use client';

import { AuthProvider } from '@/contexts/AuthContext';
import { ToastProvider } from '@/contexts/ToastContext';
import { Navbar } from '@/components/Navbar';
import { usePathname } from 'next/navigation';

export function Providers({ children }: { children: React.ReactNode }) {
    const pathname = usePathname();
    const showNavbar = pathname !== '/login';

    return (
        <AuthProvider>
            <ToastProvider>
                {showNavbar && <Navbar />}
                {children}
            </ToastProvider>
        </AuthProvider>
    );
}