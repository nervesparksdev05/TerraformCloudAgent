import React from 'react';

export const Card = ({ children, className = '', gradient = false, ...props }) => {
  const baseClasses = 'bg-dark-800 border border-white/5 rounded-2xl p-6';
  const gradientStyle = gradient ? {
    background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
    border: 'none'
  } : {};
  
  return (
    <div className={`${baseClasses} ${className}`} style={gradientStyle} {...props}>
      {children}
    </div>
  );
};

export default Card;
