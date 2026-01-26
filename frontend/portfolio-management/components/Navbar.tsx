'use client';

import { useAuth } from '@/contexts/AuthContext';
import Link from "next/link";

export const Navbar = () => {
    const { logout, user } = useAuth();

    return (
        <nav className="bg-white border-b px-6 py-4">
            <div className="flex items-center justify-between max-w-6xl mx-auto">
                <Link href="/portfolios" className="text-xl font-bold hover:text-blue-600 transition-colors">
                    Virtual Hedge Fund
                </Link>
                <div className="flex items-center gap-3">
                    <span className="text-sm text-gray-600">{user?.email}</span>
                    <button
                        onClick={logout}
                        className="px-4 py-2 text-sm border rounded-lg hover:bg-gray-50"
                    >
                        Logout
                    </button>
                </div>
            </div>
        </nav>
    );
};