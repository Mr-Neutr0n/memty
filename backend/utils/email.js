const nodemailer = require('nodemailer');

const sendWelcomeEmail = async (options) => {
    // 1) Create a transporter
    // For production, you would configure this with a real SMTP service (e.g., SendGrid, Mailgun)
    // Or a Gmail account with an App Password
    const transporter = nodemailer.createTransport({
        host: process.env.EMAIL_HOST || 'sandbox.smtp.mailtrap.io',
        port: Number(process.env.EMAIL_PORT) || 587,
        secure: process.env.EMAIL_SECURE === 'true',
        auth: {
            user: process.env.EMAIL_USERNAME,
            pass: process.env.EMAIL_PASSWORD
        },
        tls: {
            rejectUnauthorized: process.env.NODE_ENV === 'production'
        }
    });

    // 2) Define the email options
    const mailOptions = {
        from: process.env.MEMTY_EMAIL_FROM || process.env.EMAIL_FROM || 'Memty Assistant <no-reply@localhost>',
        to: options.email,
        subject: 'Welcome to Memty Assistant!',
        text: `from team Memty Assistant thank you for creating an account with Memty`,
        html: `
            <div style="font-family: Arial, sans-serif; text-align: center; color: #333;">
                <h2>Welcome to Memty Assistant! 🤖</h2>
                <p>Hi ${options.name},</p>
                <p>From the Memty Assistant team, thank you for creating an account with Memty.</p>
                <p>We are excited to have you on board. Start chatting and exploring the AI capabilities!</p>
                <br>
                <p>Best Regards,</p>
                <p><strong>Memty Team</strong></p>
            </div>
        `
    };

    // 3) Actually send the email
    try {
        await transporter.sendMail(mailOptions);
        console.log('Welcome email sent successfully to', options.email);
    } catch (err) {
        console.error('Error sending welcome email:', err);
    }
};

module.exports = sendWelcomeEmail;
