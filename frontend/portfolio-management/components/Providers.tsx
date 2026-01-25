'use client';

import { AuthProvider } from '@/contexts/AuthContext';
import { Navbar } from '@/components/Navbar';
import { usePathname } from 'next/navigation';

export function Providers({ children }: { children: React.ReactNode }) {
    const pathname = usePathname();
    const showNavbar = pathname !== '/login'; // Hide navbar on login page

    return (
        <AuthProvider>
            {showNavbar && <Navbar />}
            {children}
        </AuthProvider>
    );
}