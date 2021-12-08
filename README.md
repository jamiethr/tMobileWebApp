# tMobileWebApp

<p align="center">
  <img src="https://user-images.githubusercontent.com/74883500/144858727-6f2b5f17-3b2e-41f1-9ffa-fc2c347797e3.gif" alt="animated" />
</p>

## About

This past summer (2021), I was fortunate enough to have an internship at T-Mobile. During my internship, I was tasked with making a web app that would help employees find each other in the company. Taking direction from my manager, I taught myself MySQL, JavaScript, CSS, and HTML to create this web app.

## Goals

1. ***Create a searchable database of information that employees could use to search for different people at the company.*** <br/> The databased used organization chart data from Workday to create a basic hierarchy structure. This hierarchy structure was used to create nodes and trees (as shown above). We'd want to be able to search for people based on name, skills, job title, and other information. 
2. ***Allow users to add custom data about themselves to the database, and allow it to be searchable*** <br/> In addition to the hierarchy data from Workday, we also wanted additional data to be stored and edited by the user. This included things like their skills, job title, and more.
3. ***Have a nice-looking front-end that makes interaction painless*** <br/> Having a nice design to the web app was also something that we thought would be important. The app could potentially be used by thousands of people, so it was critical that it was easy and intuitve to use. 

## Outcomes

The final result of the project was a fully-functioning web app with the following features:
- Login screen using Okta for authentication
- Search, using MySQL backend DB
- 2D tree to visualize the relationships between individuals in a search. Each node can be clicked on to reveal more information about an individual

## Additional Notes

While the original web app also included the MySQL DB, I decided not to include it in the release (for now, at least). This was done to protect the privacy of the inviduals working at T-Mobile, though no personal data (beyond names and org chart data) was ever stored in the project before the internship concluded.
