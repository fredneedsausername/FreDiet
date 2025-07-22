# Frediet

## Inspiration

It makes no sense to use a standard diet app for my purposes. I don't follow a diet so i don't need a repeated meals feature, i don't need statistics about how much and what i eat, because my common sense can provide for the same features. I just need a place that's a bit better than excel to track how many proteins and how many calories i eat per day, so that i can know myself better and get an idea of how i eat.

## Features

The app is structured to be simple: there are accounts with logins and passwords, and there is a feature to add "meals", that simply consists of a count of proteins and calories, that are subdivided into days, following the italian timezone, and one can add records for any day and any time, with the default values being the day of the insertion and the moment of the insertion, and there is a feature to look at any range of days to see how many calories and proteins were consumed per day. It is responsive and works both on mobile and on pc.

## Stack

### Frontend
- **Structure:** Multi Page Application
- **Reactivity:** Alpine.js
- **Styling:** CSS

### Backend
- **Language:** Python
- **Framework:** Flask
- **Auth:** Cookies

### Database
- **DBMS:** MySQL
- **Connector:** PyMySQL

### Production
- **Server:** Waitress