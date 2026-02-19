import React from 'react';

export const Button = ({ 
  children, 
  variant = 'primary', 
  size = 'md',
  icon: Icon,
  className = '',
  disabled = false,
  onClick,
  ...props 
}) => {
  const baseClasses = 'inline-flex items-center justify-center gap-2 font-semibold transition-all duration-200 border-none cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed';
  
  const variants = {
    primary: 'text-white hover:-translate-y-0.5 hover:shadow-lg',
    secondary: 'bg-dark-800 text-gray-100 border border-white/5 hover:bg-white/5',
    danger: 'bg-red-500/10 text-red-500 border border-red-500/20 hover:bg-red-500/20',
    success: 'bg-green-500/10 text-green-500 border border-green-500/20 hover:bg-green-500/20',
    warning: 'bg-yellow-500/10 text-yellow-500 border border-yellow-500/20 hover:bg-yellow-500/20',
  };
  
  const sizes = {
    sm: 'px-4 py-2 text-xs rounded-lg',
    md: 'px-6 py-3 text-sm rounded-xl',
    lg: 'px-8 py-4 text-base rounded-xl',
  };

  const gradientStyle = variant === 'primary' ? {
    background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
  } : {};

  return (
    <button
      className={`${baseClasses} ${variants[variant]} ${sizes[size]} ${className}`}
      style={gradientStyle}
      disabled={disabled}
      onClick={onClick}
      {...props}
    >
      {Icon && <Icon size={size === 'sm' ? 16 : size === 'lg' ? 24 : 18} />}
      {children}
    </button>
  );
};

export default Button;
